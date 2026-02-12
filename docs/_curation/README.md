# Documentation Curation Workspace

This folder implements the execution artifacts from `docs/DOCUMENTATION_CURATION_PLAN.md`.

## Contents

- `inventory.csv` — full Markdown inventory with type, owner, and status tags.
- `audit_findings.md` — prioritized (P0/P1/P2) findings from current-repo doc validation.
- `style_guide.md` — standards for doc structure, formatting, and terminology.
- `ownership_matrix.md` — domain ownership and review cadence.
- `templates/` — reusable page templates for new/updated documentation.

## Operating Model

1. Update `inventory.csv` whenever docs are added/removed.
2. Track fixes in `audit_findings.md` and close findings by linking PRs.
3. Require template + style-guide compliance for substantial docs changes.
4. Review ownership matrix quarterly and after team changes.
