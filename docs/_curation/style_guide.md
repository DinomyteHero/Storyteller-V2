# Documentation Style Guide

## 1. Page taxonomy

Every page must declare one primary type:

- Tutorial
- Concept
- How-to
- Reference
- Runbook
- Contributor

## 2. Required section scaffolds

### How-to / Runbook pages

1. **Who this is for**
2. **Prerequisites**
3. **Steps**
4. **Validation**
5. **Troubleshooting** (runbook required)
6. **Related docs**

### Reference pages

1. **Purpose**
2. **Inputs / parameters / schema**
3. **Examples**
4. **Edge cases / constraints**
5. **Related docs**

## 3. Formatting standards

- Use ATX headings (`#`, `##`, `###`) with sentence case.
- Always label code blocks with language (`bash`, `json`, `yaml`, etc.).
- Prefer copy/paste-ready commands (no ellipses in executable lines).
- Keep line length readable (target ~100 chars).
- Use bullets for lists of options/flags.

## 4. Command conventions

- Use `bash` for shell snippets unless explicitly PowerShell/CMD.
- Prefer `python run_app.py --dev` as the default local launch command.
- When a command depends on cwd, state it explicitly above the block.
- Pair important commands with a verification command.

## 5. Terminology

Use these canonical terms consistently:

- **Era Pack** (capitalized, two words)
- **Campaign**
- **Director** / **Narrator**
- **RAG lanes**
- **Event sourcing**
- **Turn**

Avoid mixing with deprecated aliases unless documenting migration behavior.

## 6. Quality bars before merge

- Internal links resolve.
- Commands reference existing modules/files/scripts.
- New or changed behavior has docs impact reviewed.
- If content is intentionally legacy/historical, include a status banner.
