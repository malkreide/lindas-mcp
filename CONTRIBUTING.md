# Contributing

[🇩🇪 Deutsche Version](CONTRIBUTING.de.md)

Thanks for your interest in `lindas-mcp`. This is a read-only MCP server over the
public LINDAS SPARQL endpoint; contributions should keep it that way.

## Ground rules

- **Read-only.** Every tool stays annotated `readOnlyHint: true`,
  `destructiveHint: false`. No write, send, or filesystem capability. Queries go
  to the read-only `/query` endpoint only; the store's update endpoint is never
  contacted.
- **One egress host.** Requests go only to the fixed endpoint
  `https://lindas.admin.ch/query`, enforced by the `ALLOWED_HOSTS` allow-list in
  `src/lindas_mcp/lindas/client.py` (see [`docs/network-egress.md`](docs/network-egress.md));
  no tool accepts a user-supplied URL.
- **Anchor every query.** LINDAS times out on unanchored scans. Every SPARQL
  template is anchored on a known class (`?x a cube:Cube`); never add a bare
  `SELECT * WHERE { ?s ?p ?o }`. The `run_sparql` escape hatch stays capped
  (500 rows, 30 s) and marked advanced.
- **No secrets.** The read endpoint is unauthenticated; do not add credential
  handling.

## Layering

Keep the `lindas/` package layered so it can be lifted into other LINDAS-backed
servers unchanged:

- `client.py` — raw SPARQL over HTTP; knows nothing of cubes.
- `queries.py` — anchored SPARQL templates.
- `cube.py` — the cube.link vocabulary guardrail, two-phase access, and
  code→label resolution.

Tools in `server.py` talk only to `cube.py`; raw SPARQL never reaches the agent
except through `run_sparql`.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

PYTHONPATH=src pytest tests/ -m "not live"   # offline, respx-mocked
PYTHONPATH=src pytest tests/ -m live         # hits the real endpoint
ruff check src tests
```

The live suite earns its place: the `observationSet` indirection (a cube's
observations hang off `cube:observationSet`, never directly off the cube) is a
structural assumption a mock cannot validate.

## Pull requests

- Add tests for user-facing changes; keep `ruff check` and the offline suite green.
- If you add, rename, or change a tool's argument surface, regenerate
  `tool-definitions.lock.json` (the SEC-022 CI check fails otherwise) and note it
  in `CHANGELOG.md`.
- Add a `CHANGELOG.md` entry under `[Unreleased]`.
- Update both `README.md` and `README.de.md` for any documentation change.
- For release/publishing, see [`PUBLISHING.md`](PUBLISHING.md).

## Reporting security issues

See [`SECURITY.md`](SECURITY.md) — please use private reporting, not public issues.
