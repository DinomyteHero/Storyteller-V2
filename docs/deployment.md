# Deployment Guide

## Quick Start with Docker

The fastest way to deploy Storyteller-V2 on a new machine:

```bash
# 1. Clone the repository
git clone <repo-url> && cd Storyteller-V2

# 2. Copy and configure environment
cp .env.production.example .env
# Edit .env — set STORYTELLER_API_TOKEN and STORYTELLER_CORS_ALLOW_ORIGINS

# 3. Start all services
docker compose up --build -d

# 4. Pull required Ollama models (first time only)
docker compose exec ollama ollama pull mistral-nemo:latest
docker compose exec ollama ollama pull qwen3:4b
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama pull nomic-embed-text

# 5. Run ingestion (if you have lore content)
docker compose exec api python -m ingestion.ingest_lore

# 6. Verify
curl http://localhost:8000/health
curl http://localhost:8000/health/detail
```

## Manual Setup (Without Docker)

### Prerequisites
- Python 3.11+
- Node.js 20+ (for frontend)
- Ollama installed and running

### Backend
```bash
# Option A: one-command bootstrap
bash scripts/bootstrap.sh

# Option B: manual
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.production.example .env  # Edit as needed
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install && npm run build
# Built files are served automatically by the backend at /
```

### Ollama Models
```bash
ollama pull mistral-nemo:latest
ollama pull qwen3:4b
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

## Runtime verification

- List resumable campaigns:

```bash
curl http://localhost:8000/v2/campaigns
```

- Turn contract now includes prompt pack versions under `turn_contract.meta.prompt_versions` for reproducibility auditing.

## Production Checklist

- [ ] `STORYTELLER_DEV_MODE=0`
- [ ] `STORYTELLER_API_TOKEN` set to a strong random value
- [ ] `STORYTELLER_CORS_ALLOW_ORIGINS` restricted to your domain
- [ ] Database file is on persistent storage (not ephemeral container filesystem)
- [ ] Ollama has GPU access (check with `ollama list`)
- [ ] Era packs are present in `data/static/era_packs/`
- [ ] Ingestion has been run at least once

## Backup and Restore

### SQLite Database
```bash
# Backup
cp data/storyteller.db data/storyteller.db.backup.$(date +%Y%m%d)

# Restore
cp data/storyteller.db.backup.YYYYMMDD data/storyteller.db
```

### LanceDB Vector Store
```bash
# Backup (it's a directory)
tar -czf lancedb-backup-$(date +%Y%m%d).tar.gz data/lancedb/

# Restore
tar -xzf lancedb-backup-YYYYMMDD.tar.gz
```

### Full Data Backup
```bash
tar -czf storyteller-data-$(date +%Y%m%d).tar.gz data/
```

## Architecture Notes

- **Single-writer assumption**: SQLite is single-writer. Don't run multiple API instances pointing to the same DB.
- **Vector DB locality**: LanceDB requires local filesystem access. For multi-instance deployments, use a shared filesystem or switch to a networked vector DB.
- **Ollama scaling**: For multiple concurrent users, consider running Ollama on a dedicated GPU server and pointing `OLLAMA_BASE_URL` to it.
