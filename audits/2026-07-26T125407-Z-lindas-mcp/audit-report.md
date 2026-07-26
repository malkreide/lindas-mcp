# MCP-Server Audit-Report — `lindas-mcp`

**Audit-Datum:** 2026-07-26
**Skill-Version:** 1.0.0
**Catalog-Version:** 091f446b2796

---

## 1. Executive Summary

Server `lindas-mcp` wurde gegen 43 anwendbare Best-Practice-Checks geprüft. 29 bestanden, 11 Findings dokumentiert (0 critical, 6 high, 5 medium, 0 low). Production-Readiness: erreicht.

**Production-Readiness:** YES

---

## 2. Profil-Snapshot

| Feld | Wert |
|---|---|
| Server-Name | `lindas-mcp` |
| Audit-Datum | 2026-07-26 |
| Skill-Version | 1.0.0 |
| Catalog-Version | 091f446b2796 |

---

## 3. Applicability

### Status pro Kategorie

| Kategorie | Pass | Fail | Partial | Todo | N/A |
|---|---|---|---|---|---|
| ARCH | 7 | 1 | 3 | 0 | 0 |
| CH | 1 | 0 | 0 | 0 | 0 |
| OBS | 2 | 1 | 1 | 1 | 0 |
| OPS | 3 | 0 | 0 | 0 | 0 |
| SCALE | 2 | 0 | 0 | 2 | 0 |
| SDK | 1 | 0 | 3 | 0 | 0 |
| SEC | 13 | 0 | 2 | 0 | 0 |
| **Total** | **29** | **2** | **9** | **3** | **0** |

---

## 4. Findings-Übersicht

_Policy: `fail-or-partial`_

| ID | Category | Severity | Status |
|---|---|---|---|
| ARCH-009 | ARCH | high | partial |
| OBS-002 | OBS | high | partial |
| SDK-001 | SDK | high | partial |
| SDK-004 | SDK | high | partial |
| SEC-018 | SEC | high | partial |
| SEC-022 | SEC | high | partial |
| ARCH-003 | ARCH | medium | fail |
| ARCH-011 | ARCH | medium | partial |
| ARCH-012 | ARCH | medium | partial |
| OBS-003 | OBS | medium | fail |
| SDK-003 | SDK | medium | partial |

**Gesamt:** 11 Findings

---

## 5. Detail-Findings

### ARCH-003

## Finding: ARCH-003 — «Not Found» Anti-Pattern: Heuristiken statt leerer Antworten

**Severity:** medium
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** ARCH-003 (fail)
**PDF-Reference:** Sec 2.2

### Observed Behavior
`cube.search()` and `resolve_municipality()` return an empty list on no match; result models carry no `match_type` field and there is no fuzzy fallback, suggestion, or actionable note.

### Expected Behavior
Empty results should carry a `match_type` (exact/none) and an actionable next-step note (or a fuzzy/suggestion fallback), so the agent can distinguish a real miss from a malformed query and knows what to try next.

### Evidence
- src/lindas_mcp/lindas/cube.py — search() returns published[:limit] / empty list on no match, no fuzzy fallback and no suggestions
- cube.py — resolve_municipality() returns [] on no match with no fuzzy/suggestion mechanism
- models.py — CubeSearchResult/MunicipalityResult have no match_type field; grep for match_type|fuzzy|suggest returns NONE

### Gaps
- No match_type field (exact/fuzzy/none) on search results
- Empty results trigger neither a fuzzy-match nor a suggestion mechanism, and no actionable 'note' on empty results

### Risk Description
The agent gets a bare empty result and may hallucinate, retry blindly, or report 'no data' when a near-match exists.

### Remediation
Empty results should carry a `match_type` (exact/none) and an actionable next-step note (or a fuzzy/suggestion fallback), so the agent can distinguish a real miss from a malformed query and knows what to try next.

### Effort Estimate
S


### ARCH-009

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


### ARCH-011

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


### ARCH-012

## Finding: ARCH-012 — protocolVersion-Pinning + CHANGELOG + SDK-Update-Disziplin

**Severity:** medium
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** ARCH-012 (partial)
**PDF-Reference:** Anhang A9

### Observed Behavior
`FastMCP("lindas-mcp")` is created with no `protocol_version` argument (SDK default is used); the README has no MCP-protocol-version / breaking-change policy section. CHANGELOG + Dependabot are present.

### Expected Behavior
Pin the negotiated MCP `protocolVersion` (or document the SDK-managed range) and add a short 'MCP Protocol Version' / breaking-change policy to the README so SDK upgrades are a reviewed decision.

### Evidence
- server.py:47 — mcp = FastMCP('lindas-mcp'); no protocol_version argument; grep for protocol_version|protocolVersion returns NONE
- CHANGELOG.md present in Keep-a-Changelog + SemVer format
- .github/dependabot.yml — pip ecosystem monthly ('keep protocol support current')

### Gaps
- protocolVersion not pinned in server code (takes SDK default)
- CHANGELOG entries do not reference any MCP spec/protocol-version bump
- README has no 'MCP Protocol Version' section and no spec-update/breaking-change policy

### Risk Description
An SDK upgrade can silently change the negotiated protocol version and break clients without a reviewed decision.

### Remediation
Pin the negotiated MCP `protocolVersion` (or document the SDK-managed range) and add a short 'MCP Protocol Version' / breaking-change policy to the README so SDK upgrades are a reviewed decision.

### Effort Estimate
S


### OBS-002

## Finding: OBS-002 — Mask Error Details: keine Stacktraces / SQL ans LLM

**Severity:** high
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** OBS-002 (partial)
**PDF-Reference:** Sec 6.2

### Observed Behavior
FastMCP is initialised without `mask_error_details=True`. Error text is bounded (upstream diagnostic truncated) and there are no secrets to leak, but an unexpected exception would surface its raw Python message to the LLM.

### Expected Behavior
Initialise FastMCP with `mask_error_details=True` (or an equivalent wrapper) so unexpected exceptions return a generic message to the LLM while full detail is logged server-side.

### Evidence
- grep across src/ — no traceback / format_exc / sys.exc_info; no tool returns a stacktrace or raw exception dict
- SparqlError message bounded to resp.text.strip()[:400]; api_status truncates to str(exc)[:200] — bounded, surfaces only public upstream diagnostics
- No authentication and a single hard-coded public endpoint — no credentials/tokens/DB schema/file paths to leak

### Gaps
- FastMCP is initialized without mask_error_details=True — an unhandled/unexpected exception in a tool would surface its raw Python message to the LLM via the framework default
- No server-side log sink exists, so original error details are not preserved anywhere

### Risk Description
An unexpected exception could surface internal Python detail to the LLM (low impact here — no secrets, bounded text — but not defence-in-depth).

### Remediation
Initialise FastMCP with `mask_error_details=True` (or an equivalent wrapper) so unexpected exceptions return a generic message to the LLM while full detail is logged server-side.

### Effort Estimate
S


### OBS-003

## Finding: OBS-003 — Structured Logging mit RFC 5424 Severity-Stufen

**Severity:** medium
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** OBS-003 (fail)
**PDF-Reference:** Sec 6.3

### Observed Behavior
The server has no logging framework at all (no `logging`/`structlog` dependency, no logger, no per-tool-call structured events). It deliberately stays silent to keep stdout clean, but there is no structured, severity-levelled observability.

### Expected Behavior
Add a stderr-bound structured logger (e.g. structlog JSON) with RFC 5424 severity levels and per-tool-call context (tool name, duration, outcome). Keep stdout reserved for the JSON-RPC stream.

### Evidence
- pyproject.toml — no structlog/loguru/logging framework declared
- grep -rnE 'import logging|structlog|logger' src/ — NONE; the server has no logging module at all
- src/lindas_mcp/server.py — the only textual output is a single print(..., file=sys.stderr) startup warning, not structured logging
- No per-tool-call logging with tool name / session_id / correlation_id

### Gaps
- No structured logger dependency; no JSON/logfmt output, no RFC 5424 severity levels; no bound context per tool call
- The server deliberately emits nothing to keep the JSON-RPC stream clean, but OBS-003 is genuinely not met

### Risk Description
No structured logs means incidents on a hosted deployment cannot be traced or fed to a SIEM; debugging is blind.

### Remediation
Add a stderr-bound structured logger (e.g. structlog JSON) with RFC 5424 severity levels and per-tool-call context (tool name, duration, outcome). Keep stdout reserved for the JSON-RPC stream.

### Effort Estimate
M


### SDK-001

## Finding: SDK-001 — FastMCP Lifespan via @asynccontextmanager + AsyncExitStack

**Severity:** high
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** SDK-001 (partial)
**PDF-Reference:** Sec 3.1

### Observed Behavior
There is no FastMCP `lifespan`; `build_client()` returns a fresh `httpx.AsyncClient` per tool call (`async with build_client()`). Lifecycle is correct (clients are closed) but there is no pooled, long-lived client shared across calls.

### Expected Behavior
Add a FastMCP `lifespan` (`@asynccontextmanager`) that builds one `httpx.AsyncClient` and installs it as a shared, pooled client for the process; fall back to a per-call client only in direct unit tests.

### Evidence
- src/lindas_mcp/server.py:47 — mcp = FastMCP("lindas-mcp") constructed with NO lifespan= argument
- grep for asynccontextmanager|lifespan|AsyncExitStack across src/ returns NONE
- src/lindas_mcp/lindas/client.py:76-88 — build_client() returns a brand-new httpx.AsyncClient on every call; no pooling reuse across tool calls
- src/lindas_mcp/server.py — every tool opens `async with build_client() as http`, i.e. a fresh HTTP client per tool invocation

### Gaps
- Agent: fail. Reconciled to partial — per-call client lifecycle is correct (async with) but not pooled via a lifespan (peer i14y-mcp implements a shared pooled client).
- No @asynccontextmanager lifespan; FastMCP constructor lacks lifespan=
- HTTP client created per tool call instead of once on server.state; no cross-call connection pooling

### Risk Description
A new TCP/TLS handshake per tool call adds latency and, under load, connection churn; no shared resource lifecycle.

### Remediation
Add a FastMCP `lifespan` (`@asynccontextmanager`) that builds one `httpx.AsyncClient` and installs it as a shared, pooled client for the process; fall back to a per-call client only in direct unit tests.

### Effort Estimate
M


### SDK-003

## Finding: SDK-003 — Context Injection für Progress Reports und Logging

**Severity:** medium
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** SDK-003 (partial)
**PDF-Reference:** Sec 3.1

### Observed Behavior
No tool injects a `Context` parameter; there are no `ctx.report_progress()` / `ctx.info()` calls, although `run_sparql`/`search_cubes` can block for seconds up to the 45 s client timeout.

### Expected Behavior
Inject `ctx: Context | None = None` into the tools and emit `ctx.debug`/`ctx.report_progress` around the SPARQL calls, so hosts get progress and structured logging for long-running queries.

### Evidence
- grep for Context|ctx across src/ returns NONE — no tool declares a ctx: Context parameter
- grep for report_progress|ctx.info|ctx.warning returns NONE
- src/lindas_mcp/server.py — run_sparql caps runtime at 30s with no Context/progress
- src/lindas_mcp/lindas/client.py:41 — TIMEOUT_S=45.0; SPARQL tools routinely block seconds with no progress notification

### Gaps
- Agent: fail. Reconciled to partial — tools are single awaited calls that work without Context, but no ctx/progress observability (peer i14y-mcp injects Context).
- No Context parameter injected into any tool despite tools that can run 20-45s
- Mitigating: tool bodies are single awaited network calls and do not use print()/stdlib logging, so stdout is not polluted

### Risk Description
Long SPARQL queries appear to hang to the host; no progress or structured per-call logging for observability.

### Remediation
Inject `ctx: Context | None = None` into the tools and emit `ctx.debug`/`ctx.report_progress` around the SPARQL calls, so hosts get progress and structured logging for long-running queries.

### Effort Estimate
M


### SDK-004

## Finding: SDK-004 — CORS Mcp-Session-Id Exposure bei HTTP/SSE

**Severity:** high
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** SDK-004 (partial)
**PDF-Reference:** Sec 3.1

### Observed Behavior
`build_http_app()` correctly exposes `Mcp-Session-Id` via CORS, but `allow_origins=["*"]` is a hardcoded wildcard rather than an explicit, env-configurable origin list for production.

### Expected Behavior
Source allowed CORS origins from an env var (e.g. `ALLOWED_ORIGINS`) with a safe default, instead of a hardcoded `*`, so production can restrict browser origins while keeping `Mcp-Session-Id` exposed.

### Evidence
- src/lindas_mcp/server.py — build_http_app() wraps mcp.sse_app()/streamable_http_app() with CORSMiddleware
- expose_headers=["Mcp-Session-Id"] present (the critical header exposure IS met)
- allow_headers=["*", "Mcp-Session-Id"]; allow_methods=[GET, POST, DELETE, OPTIONS]
- allow_origins=["*"] hardcoded wildcard, not env-driven

### Gaps
- allow_origins=["*"] is a hardcoded wildcard — pass criterion prefers an explicit origin list / env-configurable origins for production
- allow_credentials not set (default False), so the wildcard is CORS-legal, but production-origin-hardening is unmet

### Risk Description
Wildcard CORS origins allow any browser origin to reach a hosted server; with credentials off and public data the impact is low, but it is not production-hardened.

### Remediation
Source allowed CORS origins from an env var (e.g. `ALLOWED_ORIGINS`) with a safe default, instead of a hardcoded `*`, so production can restrict browser origins while keeping `Mcp-Session-Id` exposed.

### Effort Estimate
S


### SEC-018

## Finding: SEC-018 — Input-Validation an Tool-Boundaries (Pydantic strict / Zod)

**Severity:** high
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** SEC-018 (partial)
**PDF-Reference:** Sec 3 / Sec 4

### Observed Behavior
Tool args are typed (incl. `Literal` for language) and numeric ranges are clamped via `_clamp`, but there are no schema-level `Field(ge=/le=/min_length=/max_length=)` constraints and no length bounds on string args; `run_sparql` accepts arbitrary SPARQL. Input models do not set `extra="forbid"`/`strict`.

### Expected Behavior
Move range/length limits into the schema with `Annotated[..., Field(ge=, le=, min_length=, max_length=)]` (reject out-of-range as a ValidationError instead of clamping), bound string args, and keep `run_sparql` capped + marked advanced.

### Evidence
- (see verification-results.json)

### Gaps
- (none)

### Risk Description
Malformed or oversized inputs are clamped rather than rejected; the raw-SPARQL surface of run_sparql is broad. Low security impact (read-only, capped) but weaker defence-in-depth than schema-level validation.

### Remediation
Move range/length limits into the schema with `Annotated[..., Field(ge=, le=, min_length=, max_length=)]` (reject out-of-range as a ValidationError instead of clamping), bound string args, and keep `run_sparql` capped + marked advanced.

### Effort Estimate
M


### SEC-022

## Finding: SEC-022 — Tool-Hash-Pinning + Namespace-Präfix gegen Rug Pull

**Severity:** high
**Status:** open
**Server:** lindas-mcp
**Check-Reference:** SEC-022 (partial)
**PDF-Reference:** Anhang B4

### Observed Behavior
A committed `tool-definitions.lock.json` + `tool_manifest()` + CI test guard against silent rug-pulls, but tool names have no namespace prefix (`search_cubes`, not `lindas__search_cubes`), so cross-server tool-shadowing protection is absent.

### Expected Behavior
Namespace tool names with a `lindas__` (or `lindas.`) prefix so they cannot shadow another server's tools when aggregated behind a shared gateway; regenerate the lock file and note it in the CHANGELOG.

### Evidence
- (see verification-results.json)

### Gaps
- (none)

### Risk Description
Without a namespace prefix, a malicious co-hosted server could register a same-named tool and shadow lindas's, redirecting calls.

### Remediation
Namespace tool names with a `lindas__` (or `lindas.`) prefix so they cannot shadow another server's tools when aggregated behind a shared gateway; regenerate the lock file and note it in the CHANGELOG.

### Effort Estimate
S


---

## 6. Remediation-Plan

### Empfohlene Reihenfolge

1. **ARCH-009** (high, partial)
2. **OBS-002** (high, partial)
3. **SDK-001** (high, partial)
4. **SDK-004** (high, partial)
5. **SEC-018** (high, partial)
6. **SEC-022** (high, partial)
7. **ARCH-003** (medium, fail)
8. **ARCH-011** (medium, partial)
9. **ARCH-012** (medium, partial)
10. **OBS-003** (medium, fail)
11. **SDK-003** (medium, partial)

---

## 7. Audit-Metadata

| Feld | Wert |
|---|---|
| skill_version | `1.0.0` |
| catalog_version | `091f446b2796` |
| policy | `fail-or-partial` |
| audit_date | `2026-07-26` |


_Generated by tools/build_report.py — do not edit by hand._
