# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Portfolio-standard repository structure: `CONTRIBUTING.md`/`.de`,
  `SECURITY.md`/`.de`, `EXAMPLES.md`, `PUBLISHING.md`, `docs/network-egress.md`,
  `docs/roadmap.md`, `Dockerfile`, `compose.yaml`, `.dockerignore`, `.gitignore`,
  `claude_desktop_config.json`, `server.json` (MCP Registry metadata), and
  `.github/` workflows (`ci`, `live`, `publish`) + `dependabot.yml`.
- `tool-definitions.lock.json` with a SEC-022 CI integrity check: a committed
  hash snapshot of every tool name and its argument surface, verified by
  `server.tool_manifest()` so a silent rug-pull fails the build.
- Full `mcp-audit` run under `audits/2026-07-26T125407-Z-lindas-mcp/`
  (production-ready; 11 hardening findings).
- **Audit remediation — structured logging (OBS-003):** stderr-bound JSON logs
  via `structlog` (`logging_config.py`), per-tool-call events (tool, duration,
  outcome) and a `LOG_LEVEL` env var. stdout stays reserved for JSON-RPC.
- **Audit remediation — not-found heuristics (ARCH-003):** `search_cubes` and
  `resolve_municipality` now return `match_type` (`exact`/`none`) and an
  actionable `suggestion` on an empty result.
- **Audit remediation — `Context` injection (SDK-003):** tools accept a `Context`
  and emit progress/debug events for long-running SPARQL calls.

### Changed
- **Egress hardening (SEC-021):** added a code-layer `ALLOWED_HOSTS` allow-list
  and `assert_host_allowed()` in `lindas/client.py`; the HTTP client now uses
  `follow_redirects=False` so an off-host redirect is surfaced as an error.
- **Binding default (SEC-016):** the SSE / streamable-http transport now defaults
  `HOST` to `127.0.0.1` (loopback) instead of `0.0.0.0`; binding to all
  interfaces is an explicit opt-in and prints a stderr warning. The container
  image sets `HOST=0.0.0.0` deliberately.
- **Connection pooling (SDK-001):** a single `httpx` client is now built once by
  a FastMCP `lifespan` and shared across all tool calls (`client_session()`),
  instead of a fresh client per call. Direct unit-test calls fall back to a
  per-call client.
- **Tool annotations (ARCH-009):** all tools now also set `idempotentHint: true`
  and `openWorldHint: true`.
- **Schema-level input validation (SEC-018):** tool arguments use
  `Annotated[..., Field(ge=/le=/min_length=/max_length=)]` — out-of-range inputs
  are rejected as a `ValidationError` at the boundary instead of being clamped.
- **Error masking (OBS-002):** unexpected exceptions are logged server-side and
  surfaced to the LLM as a generic message; `SparqlError`/`UpstreamError` (which
  carry only the public endpoint's own diagnostics) still propagate unchanged.
- **CORS (SDK-004):** the HTTP transport serves a CORS-wrapped app exposing the
  `Mcp-Session-Id` header, with origins configurable via `ALLOWED_ORIGINS`
  (comma-separated; default `*`) instead of a hardcoded wildcard.
- Documented the single-file `server.py` rationale (ARCH-011) and the MCP
  protocol-version policy (ARCH-012).
- Aligned `pyproject.toml` to the portfolio floor (`mcp>=1.28.1`, `structlog`,
  Python 3.13 classifier, `Issues` URL).

## [0.1.0] — 2026-07-21

### Added
- Initial release. 7 read-only tools over the LINDAS SPARQL endpoint:
  `search_cubes`, `get_cube_structure`, `query_cube_observations`,
  `list_publishers`, `resolve_municipality`, `run_sparql`, `api_status`.
- Three-layer, extraction-ready `lindas/` package: `client.py` (raw SPARQL/HTTP),
  `queries.py` (anchored templates), `cube.py` (vocabulary guardrail).
- Two-phase cube access with automatic code-to-label resolution.
- Version deduplication in `search_cubes` (`latest_only`, default on).
- Dual transport via `LINDAS_MCP_TRANSPORT`; retry 2s/4s/8s; 400 passthrough.
- Bilingual documentation (EN/DE) and full probe report in `docs/probe-lindas.md`.

### Known findings
Discovered during the live probe on 2026-07-21.

- **Broad SPARQL times out.** `COUNT(*)` over the whole store and `DISTINCT ?g`
  over all named graphs ran 70–90 s into a timeout (HTTP 000). The same question
  anchored on `?x a cube:Cube` answers in ~2 s. Every template is anchored;
  `run_sparql` warns and caps runtime.
- **Observations hang off `cube:observationSet`, never directly off the cube.**
  The naive `?cube cube:observation ?obs` returns zero rows. Caught by a live
  test, not by mocks.
- **Dimension values are codes, not labels** (region `1805`, level `4`). Code
  lists resolve via `sh:in → rdf:rest*/rdf:first → schema:name`. Cantons are
  coded as `ld.admin.ch/canton/<n>` even without an sh:in list; the bare number
  is surfaced.
- **Cubes are versioned in the URI** (`.../cube/2024-1`) with `schema:version`
  and `schema:creativeWorkStatus`. Search deduplicates to the newest published.
- **Licences are per cube and often Fedlex URIs** (`fedlex.data.admin.ch/eli/cc/`),
  which doubles as a join to fedlex-mcp.
- **Publishers deduplicate cleanly on `dcterms:creator`** (a single URI), not on
  `schema:publisher` (multilingual, splits one body into several rows).

[0.1.0]: https://github.com/malkreide/lindas-mcp/releases/tag/v0.1.0
