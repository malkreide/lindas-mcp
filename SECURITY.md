# Security Policy & Posture

[🇩🇪 Deutsche Version](SECURITY.de.md)

`lindas-mcp` is a **read-only**, **no-auth**, **public-open-data** MCP server.
This document summarises its security posture and how to report a vulnerability.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository, or contact the
maintainer listed in `README.md`. Do not file public issues for exploitable
vulnerabilities.

## Posture summary

All 7 tools only issue read (`SELECT`/`ASK`) SPARQL queries against the public
LINDAS endpoint (`lindas.admin.ch/query`); there are no write, send, or
filesystem capabilities, and no personal data is processed — the server exposes
statistical cube metadata and observations only.

| Area | Control |
|---|---|
| Egress | Code-layer allow-list (`frozenset({"lindas.admin.ch"})`, not env-configurable) checked before the client is built; `follow_redirects=False` refuses any off-host redirect; no tool accepts a user-supplied URL, so there is no SSRF surface at the client. See [`docs/network-egress.md`](docs/network-egress.md) |
| TLS | httpx certificate verification is on by default and never disabled in code |
| Auth / secrets | Unauthenticated public read endpoint — no API keys, tokens or secrets are stored or forwarded. Only the read-only `/query` endpoint is contacted; the store's update endpoint is never used |
| Input | Pydantic v2 validation at all tool boundaries; row and time caps are clamped; every built-in query template is anchored on a known class (`?x a cube:Cube`) to prevent unbounded store scans |
| `run_sparql` | Advanced escape hatch, capped at 500 rows and 30 s. It forwards a raw SPARQL query to the read-only `/query` endpoint; a `SPARQL` `SERVICE` (federation) clause is executed by the upstream store, not by this server — the server itself only ever connects to `lindas.admin.ch`. Treat `run_sparql` as the one tool with a wide input surface and keep it marked advanced |
| Tools | All annotated `readOnlyHint: true`, `destructiveHint: false`; no dynamic or remote tool registration |
| Errors | A malformed query returns the endpoint's own `400` diagnostic as a structured error; transient failures retry with backoff; `api_status` always returns an evaluable state (reachable vs. down) |
| Stdout | Reserved for the JSON-RPC stream; the server emits no stray stdout logging |
| Binding | `stdio` by default (no network surface). SSE / streamable-http binds to `HOST`, **default `127.0.0.1` (loopback)**; `0.0.0.0` is an explicit opt-in (the container image sets it deliberately) and prints a stderr warning |

## Accepted risks (portfolio-level controls)

The following are handled at the MCP gateway / host layer rather than inside
this single server. Residual risk here is low because the server is read-only,
unauthenticated, and reaches only one trusted public-data endpoint.

- **Session crypto-binding** — not applicable: there is no user identity to bind,
  as the server exposes public data with no authentication.
- **Tool allow-listing & cross-server tool-poisoning detection** (SEC-014,
  SEC-015) — a gateway/host responsibility, accepted as a portfolio-level control.
  This server has no auth model and no roles, so there is nothing to gate
  server-side; its tool definitions are version-controlled, authored in-repo, and
  reviewed via PR, with no dynamic or remote tool registration. As a rug-pull
  guard, a hash snapshot of every tool name and its argument surface (argument
  names + required set) is committed to
  [`tool-definitions.lock.json`](tool-definitions.lock.json) and checked in CI
  (SEC-022), so any silent change to the tool set or a tool's contract fails the
  build. When aggregated behind a shared gateway, enable the gateway's tool
  allow-listing and tool-poisoning detection.
- **Tool-name namespacing** (SEC-022) — tool names are intentionally left
  unprefixed (`search_cubes`, not `lindas__search_cubes`) for consistency across
  the Swiss Public Data MCP portfolio. Cross-server tool-shadowing is a
  multi-server concern handled at the aggregating gateway; within this single,
  in-repo, PR-reviewed server the `tool-definitions.lock.json` hash guard already
  prevents silent tool-surface changes. Accepted as a portfolio-level control; if
  the portfolio adopts prefixing, it will be applied uniformly across all servers.
- **Network binding for hosted deployments** — the SSE / streamable-http
  transport binds to `HOST`, defaulting to `127.0.0.1` (loopback). Binding to
  `0.0.0.0` is an explicit opt-in (the container image sets it on purpose) and
  emits a stderr warning. Front any `0.0.0.0` deployment with a reverse proxy /
  gateway that enforces TLS and access control; the default transport (`stdio`)
  has no network surface at all. When served over HTTP, CORS exposes only the
  `Mcp-Session-Id` response header (required by browser MCP clients).

## Re-evaluation triggers

Revisit these acceptances if the server ever:

- gains **write** capability or starts processing **PII**, or
- adds an **authentication** model (then implement bound, TTL'd,
  server-side-invalidated session IDs and re-audit before merge), or
- registers tools **dynamically** / from remote sources, or
- is aggregated behind a shared MCP gateway (then enable the gateway's tool
  allow-listing and tool-poisoning detection).
