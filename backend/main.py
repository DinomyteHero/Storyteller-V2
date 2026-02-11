"""FastAPI main application (V2)."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api import v2_campaigns as v2_campaigns_api, starships as starships_api
from backend.app.config import DEFAULT_DB_PATH
from backend.app.core.error_handling import create_error_response, log_error_with_context
from backend.app.db.migrate import apply_schema
from shared.config import _env_flag

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _parse_cors_allowlist(raw: str) -> list[str]:
    origins = [o.strip() for o in raw.split(",") if o and o.strip()]
    if origins:
        return origins
    return [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ]


DEV_MODE = _env_flag("STORYTELLER_DEV_MODE", default=True)
API_TOKEN = os.environ.get("STORYTELLER_API_TOKEN", "").strip()
CORS_ALLOW_ORIGINS = _parse_cors_allowlist(os.environ.get("STORYTELLER_CORS_ALLOW_ORIGINS", ""))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DEV_MODE:
        if "*" in CORS_ALLOW_ORIGINS:
            raise RuntimeError(
                "Unsafe CORS config: '*' is only allowed in dev mode. "
                "Set STORYTELLER_CORS_ALLOW_ORIGINS to explicit origins."
            )
        if not API_TOKEN:
            raise RuntimeError(
                "STORYTELLER_API_TOKEN is required when STORYTELLER_DEV_MODE=0."
            )
    apply_schema(DEFAULT_DB_PATH)
    logger.info(
        "API startup complete (dev_mode=%s, auth=%s, db=%s)",
        DEV_MODE,
        "enabled" if bool(API_TOKEN) else "disabled",
        DEFAULT_DB_PATH,
    )
    yield


app = FastAPI(title="Storyteller AI API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.headers.get("X-API-Key", "").strip()


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method.upper() == "OPTIONS":
        return await call_next(request)
    if not API_TOKEN:
        return await call_next(request)
    path = request.url.path or ""
    if path in ("/", "/health"):
        return await call_next(request)
    if DEV_MODE and (path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi")):
        return await call_next(request)

    provided = _extract_token(request)
    if provided != API_TOKEN:
        error_response = create_error_response(
            error_code="AUTH_HTTP_401",
            message="Unauthorized",
            node="api",
            details={"path": path},
        )
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content=error_response)
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPExceptions with structured error responses."""
    campaign_id = None
    if hasattr(request, "path_params") and "campaign_id" in request.path_params:
        campaign_id = request.path_params.get("campaign_id")
    
    node = "api"
    if "/turn" in request.url.path:
        node = "turn"
    elif "/setup" in request.url.path:
        node = "setup"
    elif "/state" in request.url.path:
        node = "state"
    
    error_response = create_error_response(
        error_code=f"{node.upper()}_HTTP_{exc.status_code}",
        message=exc.detail,
        node=node,
        details={
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )
    return JSONResponse(status_code=exc.status_code, content=error_response)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler: return structured error responses with logging."""
    # Extract context from request
    campaign_id = None
    if hasattr(request, "path_params") and "campaign_id" in request.path_params:
        campaign_id = request.path_params.get("campaign_id")
    
    # Determine node/endpoint from path
    node = "api"
    if "/turn" in request.url.path:
        node = "turn"
    elif "/setup" in request.url.path:
        node = "setup"
    elif "/state" in request.url.path:
        node = "state"
    
    # Log error with full context and stack trace
    log_error_with_context(
        error=exc,
        node_name=node,
        campaign_id=campaign_id,
        turn_number=None,
        agent_name=request.url.path,
        extra_context={
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
        },
    )
    
    # Return structured error response
    error_code = f"{node.upper()}_ERROR"
    message = f"An error occurred: {type(exc).__name__}"
    if str(exc):
        message = str(exc)
    
    error_response = create_error_response(
        error_code=error_code,
        message=message,
        node=node,
        details={
            "exception_type": type(exc).__name__,
            "path": request.url.path,
        },
    )
    
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_response)

# V2 is the official path (LangGraph engine)
app.include_router(v2_campaigns_api.router)
app.include_router(starships_api.router)


@app.get("/")
async def root():
    return {"message": "Storyteller AI API", "version": "2.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Serve SvelteKit static build in production.
# The `frontend/build/` folder is produced by `npm run build` (adapter-static).
# Must be mounted LAST so API routes take priority.
_FRONTEND_BUILD = Path(__file__).resolve().parent.parent / "frontend" / "build"
if _FRONTEND_BUILD.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_BUILD), html=True), name="frontend")
    logger.info("Serving SvelteKit frontend from %s", _FRONTEND_BUILD)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
