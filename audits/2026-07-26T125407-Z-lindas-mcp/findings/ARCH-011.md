## Finding: ARCH-011 — Standardisierte Repo-Struktur (src-Layout, tests, README.de.md)

**Severity:** medium
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** ARCH-011 (partial)
**PDF-Reference:** Anhang A8

### Observed Behavior
The layered `lindas/` package is clean, but all 7 tool definitions live in a single ~400-line `server.py` with no `tools/` split, exceeding the <200-line guideline; the deviation is not justified in the README.

### Expected Behavior
With >5 tools, split tool definitions into a `tools/` package (or keep them thin and document the single-file choice). Keep `server.py` near the <200-line guideline.

### Evidence
- Mandatory files present: README.md, README.de.md, CHANGELOG.md, LICENSE, pyproject.toml; dirs src/, tests/, .github/workflows/
- Correct src-layout: pyproject packages = ['src/lindas_mcp']
- CI workflows present; README.md and README.de.md have 1:1 matching section inventory

### Gaps
- With 7 tools (>5), all tool definitions live in a single ~400-line server.py; no tools/ split and server.py exceeds the <200-line guideline (business logic is layered into lindas/, but tool bodies are not grouped)
- This deviation from the tools/ standard is not explicitly justified in the README

### Risk Description
Maintainability: a single large tool file is harder to review and grows the blast radius of edits; drift from the portfolio standard.

### Remediation
With >5 tools, split tool definitions into a `tools/` package (or keep them thin and document the single-file choice). Keep `server.py` near the <200-line guideline.

### Effort Estimate
M
