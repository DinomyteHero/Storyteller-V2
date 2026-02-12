# Documentation Ownership Matrix

| Domain | Primary owner | Backup owner | Review cadence | Triggered updates |
|---|---|---|---|---|
| Getting Started (`README.md`, `QUICKSTART.md`) | Developer Experience | Backend Team | Monthly | setup flow changes, launcher changes |
| Concepts (`docs/00-09`, architecture docs) | Architecture | Backend Team | Quarterly | major pipeline changes, model orchestration changes |
| How-to Guides (pack authoring, ingestion, user guide) | Content Team | Data Platform | Monthly | ingestion command changes, authoring schema changes |
| Reference (API, schemas, env vars) | Backend Team | Architecture | Monthly | endpoint additions/changes, config changes |
| Operations / Runbooks (`docs/RUNBOOK.md`) | Platform Ops | Developer Experience | Monthly | deployment/runtime behavior changes |
| Contributor Docs (plans, implementation notes) | Architecture | Developer Experience | Quarterly | roadmap/consolidation updates |

## Review process

1. Open one curation issue per review cycle.
2. Re-run inventory + freshness checks.
3. Update statuses in `inventory.csv`.
4. Close or re-prioritize findings in `audit_findings.md`.
