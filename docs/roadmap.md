# Roadmap & project phase

`lindas-mcp` follows the portfolio's **Read-only First** phase architecture: a
server earns write and multi-agent capabilities only after the previous phase is
proven and audited. This keeps the security surface small while the server is
young.

## Current phase: **Phase 1 — Read-only**

All 7 tools are annotated `readOnlyHint: true`, `destructiveHint: false` and
issue only read (`SELECT`/`ASK`) SPARQL against the public LINDAS `/query`
endpoint. There is no authentication, no write/send/filesystem capability, and no
personal data. This is the intended long-term posture for a knowledge-graph
discovery server — Phase 2 is only entered if a concrete use case requires it.

| Phase | Scope | Status |
|---|---|---|
| **1 — Read-only** | Guarded discovery + two-phase cube access over the public store; stdio + SSE transport; no auth | ✅ current |
| **2 — Write** | Any write/submit capability (not currently planned) | ⛔ not started |
| **3 — Multi-agent** | Aggregation behind a shared MCP gateway | ⛔ not started |

## Phase-transition prerequisites

Moving to **Phase 2 (write)** would require, before any write tool is merged:

- an authentication model with bound, TTL'd, server-side-invalidated session IDs;
- human-in-the-loop confirmation for destructive operations (HITL checks);
- input validation hardened to strict Pydantic argument schemas (SEC-018);
- a fresh security audit (see [`../audits/`](../audits/)) with no open `critical`/`high` findings.

Moving to **Phase 3 (multi-agent / gateway)** would additionally require:

- tool-name namespacing and tool-definition hash pinning (SEC-022);
- the gateway's tool allow-listing and tool-poisoning detection enabled
  (SEC-014/SEC-015).

## Candidate improvements (read-only, no phase change)

These stay within Phase 1 and would be additive:

- **Server-side observation filtering** by dimension value where the store allows
  it cheaply, reducing reliance on `run_sparql` for simple slices.
- **Richer version handling** in `search_cubes` for unusual URI shapes.
- **Theme / dimension browsing** helpers on top of the existing cube vocabulary.

The open items from any audit run live under [`../audits/`](../audits/) as
per-finding documents; they are tracked there rather than duplicated here.
