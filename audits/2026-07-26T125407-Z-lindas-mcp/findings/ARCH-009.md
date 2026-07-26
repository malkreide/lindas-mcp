## Finding: ARCH-009 — Tool Annotations: readOnlyHint, destructiveHint, idempotentHint, openWorldHint

**Severity:** high
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** ARCH-009 (partial)
**PDF-Reference:** Anhang A5

### Observed Behavior
All 7 tools set `readOnlyHint: True, destructiveHint: False`, but `openWorldHint` and `idempotentHint` are not set, even though every tool reaches an external HTTP endpoint and is idempotent.

### Expected Behavior
Tools reaching external systems should set `openWorldHint: True`; idempotent read tools should set `idempotentHint: True`, so hosts can reason about caching and side-effects.

### Evidence
- server.py:47 — READ_ONLY = {readOnlyHint: True, destructiveHint: False}; applied explicitly to all 7 tools (no defaults)
- readOnlyHint consistent with behaviour: all tools issue only read SELECT/ASK SPARQL
- Annotations policy documented in README and docs/roadmap.md

### Gaps
- openWorldHint not set although every tool reaches an external HTTP endpoint (criterion wants openWorldHint:true)
- idempotentHint not set although these read-only queries are idempotent

### Risk Description
Hosts cannot infer that the tools are idempotent and reach an open world, losing caching / safety optimisations.

### Remediation
Tools reaching external systems should set `openWorldHint: True`; idempotent read tools should set `idempotentHint: True`, so hosts can reason about caching and side-effects.

### Effort Estimate
S
