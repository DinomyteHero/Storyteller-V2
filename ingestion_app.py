"""Legacy Python UI for local ingestion tasks (lore, style, facets, verify/query)."""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st


def _run(cmd: list[str]) -> tuple[int, str]:
    """Run a command and return (exit_code, combined_output)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        out = (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except Exception as e:
        return 1, f"Failed to run: {e}"


def _cmd_str(cmd: list[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)


def _path_exists(path_str: str) -> bool:
    return bool(path_str and Path(path_str).expanduser().exists())


def _file_summary(dir_path: str, exts: list[str], recursive: bool = False) -> tuple[int, int, list[Path]]:
    """Return (count, total_bytes, files) for extensions under dir."""
    base = Path(dir_path).expanduser()
    files: list[Path] = []
    if not base.exists():
        return 0, 0, files
    globber = base.rglob if recursive else base.glob
    for ext in exts:
        files.extend(globber(f"*{ext}"))
    total = sum(f.stat().st_size for f in files if f.exists())
    return len(files), total, sorted(files)


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n = n / 1024
    return f"{n:.1f} TB"


def _section_header(title: str, subtitle: str | None = None) -> None:
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def _write_last_ingest(vectordb_path: str, extra: dict[str, Any] | None = None) -> None:
    """Persist the last-used LanceDB path for smoother 'ingest → play' workflow."""
    try:
        payload: dict[str, Any] = {
            "vectordb_path": str(Path(vectordb_path).expanduser()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            payload.update(extra)
        out_path = Path("./data/last_ingest.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    st.set_page_config(page_title="Storyteller Ingestion Studio", layout="wide")
    st.title("Storyteller Ingestion Studio")
    st.caption("Run local ingestion and verification tasks against your LanceDB store.")
    st.caption(f"Python: {sys.executable}")

    with st.sidebar:
        st.subheader("After ingest")
        st.caption("Start the game stack (auto-uses your last LanceDB path):")
        st.code(".\\start_dev.bat", language="powershell")

    default_db = str(Path("./data/lancedb").resolve())

    tabs = st.tabs(
        [
            "Lore (Hierarchical)",
            "Lore (Flat TXT/EPUB)",
            "Style",
            "Verify / Query",
        ]
    )

    with tabs[0]:
        _section_header("Hierarchical Lore Ingest", "PDF/EPUB/TXT → parent/child chunks with context prefixes")
        input_dir = st.text_input("Input folder", value=str(Path("./data/lore").resolve()))
        db_path = st.text_input("LanceDB path", value=default_db)
        dry_run = st.checkbox("Dry run (preview only)", value=False, key="dry_hier")
        recursive = st.checkbox("Recursive (include subfolders)", value=True, key="rec_hier")
        col1, col2, col3 = st.columns(3)
        with col1:
            time_period = st.text_input("time_period (optional)", value="")
            planet = st.text_input("planet (optional)", value="")
        with col2:
            faction = st.text_input("faction (optional)", value="")
            source_type = st.text_input("source_type", value="reference")
        with col3:
            collection = st.text_input("collection", value="lore")
            book_title = st.text_input("book_title (optional)", value="")
        era_aliases = st.text_input("era_aliases (JSON optional)", value="")

        cmd = [
            sys.executable,
            "-m",
            "ingestion.ingest_lore",
            "--input",
            input_dir,
            "--db",
            db_path,
            "--source-type",
            source_type,
            "--collection",
            collection,
        ]
        if time_period:
            cmd += ["--time-period", time_period]
        if planet:
            cmd += ["--planet", planet]
        if faction:
            cmd += ["--faction", faction]
        if book_title:
            cmd += ["--book-title", book_title]
        if recursive:
            cmd += ["--recursive"]
        if era_aliases:
            cmd += ["--era-aliases", era_aliases]

        st.code(_cmd_str(cmd), language="bash")
        count, total_bytes, files = _file_summary(input_dir, [".pdf", ".epub", ".txt"], recursive=recursive)
        with st.expander("Preview files"):
            st.caption(f"{count} files • {_human_bytes(total_bytes)}")
            if count == 0:
                st.warning("No .pdf/.epub/.txt files found in this folder.")
            else:
                for f in files[:50]:
                    st.text(f.name)
                if count > 50:
                    st.text(f"... and {count - 50} more")
        if st.button("Run Hierarchical Ingest", type="primary", disabled=not _path_exists(input_dir)):
            if dry_run:
                st.info("Dry run enabled — no command executed.")
            else:
                with st.spinner("Running ingestion..."):
                    code, out = _run(cmd)
                st.success("Ingest completed." if code == 0 else "Ingest failed.")
                if code == 0:
                    _write_last_ingest(
                        db_path,
                        extra={
                            "mode": "lore_hierarchical",
                            "input_dir": input_dir,
                            "time_period": time_period,
                            "source_type": source_type,
                            "collection": collection,
                        },
                    )
                st.text(out or "(no output)")

    with tabs[1]:
        _section_header("Flat Lore Ingest", "TXT/EPUB → ~600 token chunks (no PDF)")
        input_dir = st.text_input("Input folder ", value=str(Path("./sample_data").resolve()))
        db_path = st.text_input("LanceDB path ", value=default_db)
        dry_run = st.checkbox("Dry run (preview only)", value=False, key="dry_flat")
        recursive = st.checkbox("Recursive (include subfolders) ", value=True, key="rec_flat")
        col1, col2, col3 = st.columns(3)
        with col1:
            era = st.text_input("era", value="LOTF")
            source_type = st.text_input("source_type ", value="novel")
        with col2:
            collection = st.text_input("collection ", value="novels")
            book_title = st.text_input("book_title (EPUB only)", value="")
        with col3:
            st.caption("Supported: .txt, .epub")
        era_aliases = st.text_input("era_aliases (JSON optional) ", value="")

        cmd = [
            sys.executable,
            "-m",
            "ingestion.ingest",
            "--input_dir",
            input_dir,
            "--era",
            era,
            "--source_type",
            source_type,
            "--collection",
            collection,
            "--out_db",
            db_path,
        ]
        if book_title:
            cmd += ["--book_title", book_title]
        if recursive:
            cmd += ["--recursive"]
        if era_aliases:
            cmd += ["--era-aliases", era_aliases]

        st.code(_cmd_str(cmd), language="bash")
        count, total_bytes, files = _file_summary(input_dir, [".txt", ".epub"], recursive=recursive)
        with st.expander("Preview files "):
            st.caption(f"{count} files • {_human_bytes(total_bytes)}")
            if count == 0:
                st.warning("No .txt/.epub files found in this folder.")
            else:
                for f in files[:50]:
                    st.text(f.name)
                if count > 50:
                    st.text(f"... and {count - 50} more")
        if st.button("Run Flat Ingest", type="primary", disabled=not _path_exists(input_dir)):
            if dry_run:
                st.info("Dry run enabled — no command executed.")
            else:
                with st.spinner("Running ingestion..."):
                    code, out = _run(cmd)
                st.success("Ingest completed." if code == 0 else "Ingest failed.")
                if code == 0:
                    _write_last_ingest(
                        db_path,
                        extra={
                            "mode": "lore_flat",
                            "input_dir": input_dir,
                            "era": era,
                            "source_type": source_type,
                            "collection": collection,
                        },
                    )
                st.text(out or "(no output)")

    with tabs[2]:
        _section_header("Style Ingest", "TXT/MD → style_chunks for Director")
        style_dir = st.text_input("Style folder", value=str(Path("./data/style").resolve()))
        db_path = st.text_input("LanceDB path  ", value=default_db)
        dry_run = st.checkbox("Dry run (preview only)", value=False, key="dry_style")
        cmd = [
            sys.executable,
            "-m",
            "backend.app.scripts.ingest_style",
            "--dir",
            style_dir,
            "--db",
            db_path,
        ]
        st.code(_cmd_str(cmd), language="bash")
        count, total_bytes, files = _file_summary(style_dir, [".txt", ".md"])
        with st.expander("Preview files  "):
            st.caption(f"{count} files • {_human_bytes(total_bytes)}")
            if count == 0:
                st.warning("No .txt/.md files found in this folder.")
            else:
                for f in files[:50]:
                    st.text(f.name)
                if count > 50:
                    st.text(f"... and {count - 50} more")
        if st.button("Run Style Ingest", type="primary", disabled=not _path_exists(style_dir)):
            if dry_run:
                st.info("Dry run enabled — no command executed.")
            else:
                with st.spinner("Running ingestion..."):
                    code, out = _run(cmd)
                st.success("Ingest completed." if code == 0 else "Ingest failed.")
                if code == 0:
                    _write_last_ingest(db_path, extra={"mode": "style", "style_dir": style_dir})
                st.text(out or "(no output)")

    with tabs[3]:
        _section_header("Verify / Query", "Sanity-check your lore store and run a quick search")
        db_path = st.text_input("LanceDB path    ", value=default_db)
        query = st.text_input("Sample query", value="Tatooine")

        col1, col2 = st.columns(2)
        with col1:
            verify_cmd = [
                sys.executable,
                "scripts/verify_lore_store.py",
                "--db",
                db_path,
                "--query",
                query,
            ]
            st.code(_cmd_str(verify_cmd), language="bash")
            if st.button("Run Verify", type="primary", disabled=not _path_exists(db_path)):
                with st.spinner("Running verify..."):
                    code, out = _run(verify_cmd)
                st.success("Verify completed." if code == 0 else "Verify failed.")
                st.text(out or "(no output)")
        with col2:
            k = st.number_input("Top K", min_value=1, max_value=20, value=5)
            era = st.text_input("Era (optional)", value="LOTF")
            query_cmd = [
                sys.executable,
                "-m",
                "ingestion",
                "query",
                "--query",
                query,
                "--k",
                str(k),
                "--db",
                db_path,
            ]
            if era:
                query_cmd += ["--era", era]
            st.code(_cmd_str(query_cmd), language="bash")
            if st.button("Run Query", type="primary", disabled=not _path_exists(db_path)):
                with st.spinner("Running query..."):
                    code, out = _run(query_cmd)
                st.success("Query completed." if code == 0 else "Query failed.")
                st.text(out or "(no output)")


if __name__ == "__main__":
    main()
