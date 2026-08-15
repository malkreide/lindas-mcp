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

The 7 tool definitions deliberately stay together in `server.py`: each tool body
is a thin wrapper (validate → call `cube.py` → shape the response model), and all
real logic lives in the layered `lindas/` package. A `tools/` split would add
indirection without moving any logic, so the single file is intentional rather
than accidental.

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

## The live suite: when it runs, and who sees a red result

**Cadence:** every Monday at 05:17 UTC, plus on demand via *Actions → Live API tests → Run
workflow*. See [`.github/workflows/live.yml`](.github/workflows/live.yml).

**Who sees it:** A red run opens an issue labelled `upstream` and the stable title “Live-Tests gegen lindas.admin.ch rot (<Datum>)”. A second red run recognises the open issue by its title prefix and appends to that same thread rather than opening a second one. Once the suite is green again, the issue closes itself.

**Three answers, not two.** `scripts/classify_live_run.py` reads the JUnit XML rather than
the exit code and separates `clear` (ran, green), `finding` (ran, something
fell) and `unknown` (did not run — install failed, nothing collected,
everything skipped). An `unknown` never closes an issue: closing would claim a
comparison that never happened.

**A red live run does not necessarily mean *our* bug.** It means the contract
with the source has changed, or the source is down. Both belong seen; only the
first belongs fixed. Please read the run before disabling the job — that is how
this check dies, and it is the only one in the repository that can contradict a
wrong assumption about lindas.admin.ch. Every other test asserts against a fixture, and
the fixture was written from the same assumption as the code.
