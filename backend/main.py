"""FastAPI main application (V2)."""
import logging
import os
import time as _time
from collections import defaultdict as _defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api import v2_campaigns as v2_campaigns_api, starships as starships_api
from backend.app.config import DEFAULT_DB_PATH, MODEL_CONFIG
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




def _collect_environment_diagnostics() -> dict:
    """Collect structured environment diagnostics for /health/detail."""
    import httpx
    from backend.app.config import resolve_vectordb_path, ERA_PACK_DIR, DATA_ROOT

    checks: dict[str, dict] = {}

    ollama_url = os.environ.get("OLLAMA_BASE_URL", os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        checks["ollama"] = {
            "ok": True,
            "url": ollama_url,
            "models_loaded": len(models),
        }
    except Exception as e:
        checks["ollama"] = {"ok": False, "url": ollama_url, "error": str(e)}

    data_root_ok = DATA_ROOT.exists()
    checks["data_root"] = {"ok": data_root_ok, "path": str(DATA_ROOT)}

    vdb = resolve_vectordb_path()
    checks["vector_db_path"] = {"ok": vdb.exists(), "path": str(vdb)}

    # LanceDB table existence and row counts
    lancedb_tables: dict[str, Any] = {}
    lancedb_ok = False
    if vdb.exists():
        try:
            import lancedb as _ldb
            db = _ldb.connect(str(vdb))
            table_names = db.table_names()
            for tname in sorted(table_names):
                try:
                    tbl = db.open_table(tname)
                    row_count = tbl.count_rows()
                    lancedb_tables[tname] = {"rows": row_count, "ok": row_count > 0}
                except Exception as _te:
                    lancedb_tables[tname] = {"rows": 0, "ok": False, "error": str(_te)}
            lancedb_ok = len(table_names) > 0 and any(
                t.get("ok", False) for t in lancedb_tables.values()
            )
        except Exception as _ldb_err:
            lancedb_tables["_error"] = {"ok": False, "error": str(_ldb_err)}
    checks["lancedb_tables"] = {
        "ok": lancedb_ok,
        "path": str(vdb),
        "tables": lancedb_tables,
    }

    era_dir = Path(str(ERA_PACK_DIR))
    era_pack_details: list[dict] = []
    era_ok = False
    if era_dir.exists() and era_dir.is_dir():
        for d in sorted([x for x in era_dir.iterdir() if x.is_dir()]):
            yml_count = len(list(d.glob("*.yml")) + list(d.glob("*.yaml")))
            era_pack_details.append({
                "era_id": d.name,
                "yaml_files": yml_count,
                "pack_contract_ok": yml_count >= 12,
            })
        era_ok = len(era_pack_details) > 0
    checks["era_packs"] = {
        "ok": era_ok,
        "path": str(era_dir),
        "packs": era_pack_details,
    }

    checks["llm_roles"] = {
        "ok": True,
        "configured_roles": sorted(list(MODEL_CONFIG.keys())),
    }

    overall_ok = all(v.get("ok", False) for v in checks.values())
    return {"ok": overall_ok, "checks": checks}

def _validate_environment() -> None:
    """Log environment health checks at startup. Never fails — graceful degradation."""
    import httpx
    from backend.app.config import resolve_vectordb_path, ERA_PACK_DIR, DATA_ROOT

    # Check Ollama connectivity
    ollama_url = os.environ.get("OLLAMA_BASE_URL", os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        logger.info("Ollama reachable at %s (%d models loaded)", ollama_url, len(models))
    except Exception as e:
        logger.warning("Ollama NOT reachable at %s: %s (LLM calls will fail until resolved)", ollama_url, e)

    # Check data directories
    if DATA_ROOT.exists():
        logger.info("Data root: %s (exists)", DATA_ROOT)
    else:
        logger.warning("Data root missing: %s (create with 'storyteller setup')", DATA_ROOT)

    # Check vector DB
    vdb = resolve_vectordb_path()
    if vdb.exists():
        logger.info("Vector DB: %s (exists)", vdb)
    else:
        logger.warning("Vector DB missing: %s (run ingestion first)", vdb)

    # Check era packs
    era_dir = Path(str(ERA_PACK_DIR))
    if era_dir.exists():
        yamls = list(era_dir.glob("*.yaml")) + list(era_dir.glob("*.yml"))
        if yamls:
            logger.info("Era packs: %d found in %s", len(yamls), era_dir)
        else:
            logger.warning("No era pack YAML files in %s", era_dir)
    else:
        logger.warning("Era pack directory missing: %s", era_dir)


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
    _validate_environment()
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


_RATE_LIMITS: dict[str, list[float]] = _defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10     # max turn requests per minute per IP


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple per-IP rate limiting for turn endpoints."""
    path = request.url.path or ""
    if "/turn" not in path:
        return await call_next(request)
    client_ip = request.client.host if request.client else "unknown"
    now = _time.monotonic()
    # Clean old entries
    _RATE_LIMITS[client_ip] = [t for t in _RATE_LIMITS[client_ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_RATE_LIMITS[client_ip]) >= _RATE_LIMIT_MAX:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Max 10 turn requests per minute.", "error_code": "RATE_LIMIT"},
        )
    _RATE_LIMITS[client_ip].append(now)
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


@app.get("/health/detail")
async def health_detail():
    """Structured readiness diagnostics for deployment checks."""
    diag = _collect_environment_diagnostics()
    return {"status": "healthy" if diag.get("ok") else "degraded", **diag}


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
