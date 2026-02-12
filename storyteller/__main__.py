"""Entry point for ``python -m storyteller <command>``.

Commands:
    doctor   – check environment, deps, Ollama, data dirs
    setup    – scaffold data dirs, copy .env, and run doctor checks
    dev      – start backend + SvelteKit UI (+ optional Ollama)
    ingest   – run ingestion (simple or lore pipeline)
    query    – search the vector store
    extract-knowledge – build SQLite KG tables from ingested lore
    organize-ingest – organize messy document libraries for ingestion
    models   – show resolved per-role model/provider configuration
    style-audit – audit active/deprecated style assets
    build-style-pack – auto-generate style docs from corpus
"""
from storyteller.cli import main

if __name__ == "__main__":
    main()
