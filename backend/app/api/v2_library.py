"""Library API: book ingestion, management, and world content browsing.

Phase 6: Endpoints for the /library frontend.
- GET  /v2/library/books          — list ingested documents
- POST /v2/library/ingest         — upload + ingest a file (PDF/EPUB/TXT)
- GET  /v2/library/ingest/{id}/status — poll ingestion job status

V11.0: Source management endpoints.
- GET    /v2/library/sources          — list lore sources
- POST   /v2/library/sources          — create a lore source
- DELETE /v2/library/sources/{id}     — delete a source and its chunks
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from backend.app.config import DATA_ROOT
from backend.app.db.connection import get_db, get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/library", tags=["library"])

# Upload directory for user-uploaded books
_UPLOAD_DIR = DATA_ROOT / "lore" / "uploads"


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class BookEntry(BaseModel):
    id: str
    filename: str
    status: str
    setting_id: str = ""
    period_id: str = ""
    chunk_count: int = 0
    error_message: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


class BookListResponse(BaseModel):
    items: list[BookEntry]


class IngestJobResponse(BaseModel):
    job_id: str
    filename: str
    status: str


class IngestStatusResponse(BaseModel):
    job_id: str
    status: str
    chunk_count: int = 0
    error_message: str | None = None


# ---------------------------------------------------------------------------
# GET /v2/library/books
# ---------------------------------------------------------------------------


@router.get("/books", response_model=BookListResponse)
def list_books(conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    """List all ingested documents, ordered by most recent first."""
    cursor = conn.cursor()
    try:
        rows = cursor.execute(
            "SELECT id, filename, status, setting_id, period_id, chunk_count, "
            "error_message, created_at, completed_at "
            "FROM ingestion_jobs ORDER BY created_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        # Table may not exist yet (pre-migration)
        return {"items": []}

    items = [
        {
            "id": r["id"],
            "filename": r["filename"],
            "status": r["status"],
            "setting_id": r["setting_id"] or "",
            "period_id": r["period_id"] or "",
            "chunk_count": r["chunk_count"] or 0,
            "error_message": r["error_message"],
            "created_at": r["created_at"],
            "completed_at": r["completed_at"],
        }
        for r in rows
    ]
    return {"items": items}


# ---------------------------------------------------------------------------
# POST /v2/library/ingest
# ---------------------------------------------------------------------------


@router.post("/ingest", response_model=IngestJobResponse)
async def ingest_file_endpoint(
    file: UploadFile = File(...),
    setting_id: str = Form(default=""),
    period_id: str = Form(default=""),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Upload a document and start background ingestion.

    Accepts PDF, EPUB, and TXT files. The file is saved to
    data/lore/uploads/ and ingested into LanceDB in a background thread.
    """
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in (".pdf", ".epub", ".txt"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Use .pdf, .epub, or .txt.")

    # Save uploaded file
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    safe_name = f"{job_id}_{filename}"
    dest = _UPLOAD_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)
    logger.info("Library: saved upload %s (%d bytes)", safe_name, len(content))

    # Create job record
    try:
        conn.execute(
            "INSERT INTO ingestion_jobs (id, filename, status, setting_id, period_id) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (job_id, filename, setting_id, period_id),
        )
        conn.commit()
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    # Launch background ingestion thread
    from backend.app.config import DEFAULT_DB_PATH
    _start_ingestion_worker(
        job_id=job_id,
        file_path=dest,
        setting_id=setting_id,
        period_id=period_id,
        db_path=DEFAULT_DB_PATH,
    )

    return {"job_id": job_id, "filename": filename, "status": "pending"}


# ---------------------------------------------------------------------------
# GET /v2/library/ingest/{job_id}/status
# ---------------------------------------------------------------------------


@router.get("/ingest/{job_id}/status", response_model=IngestStatusResponse)
def get_ingest_status(
    job_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Poll the status of an ingestion job."""
    row = conn.execute(
        "SELECT id, status, chunk_count, error_message FROM ingestion_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return {
        "job_id": row["id"],
        "status": row["status"],
        "chunk_count": row["chunk_count"] or 0,
        "error_message": row["error_message"],
    }


# ---------------------------------------------------------------------------
# Background ingestion worker
# ---------------------------------------------------------------------------


def _start_ingestion_worker(
    *,
    job_id: str,
    file_path: Path,
    setting_id: str,
    period_id: str,
    db_path: str,
) -> None:
    """Launch a daemon thread that ingests the uploaded file into LanceDB."""

    def _worker() -> None:
        conn = get_connection(db_path)
        try:
            # Mark job as running
            conn.execute(
                "UPDATE ingestion_jobs SET status = 'running' WHERE id = ?",
                (job_id,),
            )
            conn.commit()

            # Build metadata for the ingestion pipeline
            meta: dict[str, str] = {}
            if setting_id:
                meta["setting_id"] = setting_id
            if period_id:
                meta["period_id"] = period_id
                meta["time_period"] = period_id  # alias used by ingestion

            # Run ingestion
            from ingestion.ingest_lore import ingest_file, _to_canonical_chunks
            from ingestion.store import LanceStore
            from backend.app.config import resolve_vectordb_path, LORE_TABLE_NAME

            hierarchical = ingest_file(
                path=file_path,
                meta=meta,
                source_type="user_upload",
                collection="lore",
            )
            canonical = _to_canonical_chunks(hierarchical)

            if canonical:
                db_dir = resolve_vectordb_path()
                store = LanceStore(str(db_dir))
                result = store.add_chunks(canonical, dedupe=True)
                chunk_count = result.get("added", 0)
            else:
                chunk_count = 0

            # Mark complete
            conn.execute(
                "UPDATE ingestion_jobs SET status = 'complete', chunk_count = ?, "
                "completed_at = datetime('now') WHERE id = ?",
                (chunk_count, job_id),
            )
            conn.commit()
            logger.info("Library: ingestion job %s complete — %d chunks", job_id, chunk_count)

        except Exception as e:  # Intentional broad catch: worker thread error boundary
            logger.error("Library: ingestion job %s failed: %s", job_id, e)
            try:
                conn.execute(
                    "UPDATE ingestion_jobs SET status = 'failed', error_message = ?, "
                    "completed_at = datetime('now') WHERE id = ?",
                    (str(e)[:500], job_id),
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass
        finally:
            conn.close()

    thread = threading.Thread(
        target=_worker,
        name=f"library-ingest-{job_id}",
        daemon=True,
    )
    thread.start()


# ---------------------------------------------------------------------------
# V11.0: Lore Source management
# ---------------------------------------------------------------------------


class LoreSourceEntry(BaseModel):
    id: str
    name: str
    setting_id: str = ""
    period_id: str = ""
    file_count: int = 0
    chunk_count: int = 0
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None


class LoreSourceListResponse(BaseModel):
    items: list[LoreSourceEntry]


class LoreSourceCreateRequest(BaseModel):
    name: str
    setting_id: str = ""
    period_id: str = ""


@router.get("/sources", response_model=LoreSourceListResponse)
def list_sources(conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    """List all lore sources, ordered by most recent first."""
    try:
        rows = conn.execute(
            "SELECT id, name, setting_id, period_id, file_count, chunk_count, "
            "status, created_at, updated_at "
            "FROM lore_sources WHERE status != 'deleted' ORDER BY created_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        return {"items": []}
    items = [
        {
            "id": r["id"],
            "name": r["name"],
            "setting_id": r["setting_id"] or "",
            "period_id": r["period_id"] or "",
            "file_count": r["file_count"] or 0,
            "chunk_count": r["chunk_count"] or 0,
            "status": r["status"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return {"items": items}


@router.post("/sources", response_model=LoreSourceEntry)
def create_source(
    req: LoreSourceCreateRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Create a new lore source for grouping ingested files."""
    source_id = uuid.uuid4().hex[:12]
    try:
        conn.execute(
            "INSERT INTO lore_sources (id, name, setting_id, period_id) VALUES (?, ?, ?, ?)",
            (source_id, req.name, req.setting_id, req.period_id),
        )
        conn.commit()
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {
        "id": source_id,
        "name": req.name,
        "setting_id": req.setting_id,
        "period_id": req.period_id,
        "file_count": 0,
        "chunk_count": 0,
        "status": "active",
        "created_at": None,
        "updated_at": None,
    }


@router.delete("/sources/{source_id}")
def delete_source(
    source_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Delete a lore source and remove its chunks from LanceDB."""
    row = conn.execute(
        "SELECT id, name, setting_id, period_id FROM lore_sources WHERE id = ? AND status != 'deleted'",
        (source_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found.")

    # Mark as deleting
    conn.execute(
        "UPDATE lore_sources SET status = 'deleting', updated_at = datetime('now') WHERE id = ?",
        (source_id,),
    )
    conn.commit()

    # Delete chunks from LanceDB by source name
    deleted_chunks = 0
    try:
        from ingestion.store import LanceStore
        from backend.app.config import resolve_vectordb_path
        db_dir = resolve_vectordb_path()
        store = LanceStore(str(db_dir))
        deleted_chunks = store.delete_by_filter(source=row["name"])
    except (ImportError, FileNotFoundError, RuntimeError, OSError) as e:
        logger.warning("Failed to delete LanceDB chunks for source %s: %s", source_id, e)

    # Mark as deleted
    conn.execute(
        "UPDATE lore_sources SET status = 'deleted', updated_at = datetime('now') WHERE id = ?",
        (source_id,),
    )
    conn.commit()

    return {"deleted": True, "source_id": source_id, "chunks_removed": deleted_chunks}
