> **Part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide/swiss-public-data-mcp)** — a collection of open-source MCP servers connecting AI agents to Swiss public and open data.
> This is a private project. It is not affiliated with, endorsed by, or operated on behalf of any employer or public authority.

# lindas-mcp

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-server-orange.svg)](https://modelcontextprotocol.io/)
[![Data: LINDAS](https://img.shields.io/badge/data-LINDAS%20%7C%20SPARQL-red.svg)](https://lindas.admin.ch)

**MCP server for LINDAS — the linked-data knowledge graph of the Swiss administration.**

🇩🇪 [Deutsche Version](README.de.md)

---

## What LINDAS is

LINDAS (Linked Data Service) is the Swiss Confederation's SPARQL knowledge
graph, run by the Federal Archives. Instead of tables, it publishes data as RDF
triples: around 2000 statistical **data cubes** (cube.link) from federal
offices, plus the geo-linked data that powers visualize.admin.ch.

> **Mnemonic: «I14Y is the library catalogue, LINDAS is the library itself.»**
> [i14y-mcp](https://github.com/malkreide/i14y-mcp) tells you a dataset exists.
> LINDAS holds the data and lets you query across all of it at once.

This server wraps LINDAS in guarded tools rather than exposing raw SPARQL,
because the store rewards precise queries and times out on broad ones.

---

## 🎯 Anchor Demo Query

> *«Which forest-fire danger level currently applies, who publishes it, and
> under which licence?»*

```
search_cubes(query="waldbrand")
  → «Waldbrandgefahr» — BAFU, published

get_cube_structure(cube_uri=...)
  → dimensions: Warnregion (key), Gefahrenstufe (measure)
  → licence: fedlex.data.admin.ch/eli/cc/1984/... (a Fedlex URI!)

query_cube_observations(cube_uri=...)
  → Warnregion: "Dorneck / Thierstein (SO)", Gefahrenstufe: "grosse Gefahr"
```

The codes come back as labels — «grosse Gefahr», not `4`. And the licence is a
Fedlex URI you can resolve with [fedlex-mcp](https://github.com/malkreide/fedlex-mcp).

### Demo

![Demo: Claude using search_cubes, get_cube_structure and query_cube_observations](docs/assets/demo.svg)

---

## The two-phase access pattern

LINDAS cubes are self-describing but coded, and the server does two steps to
read them:

1. **Structure** — the cube's SHACL shape: its dimensions (filterable axes),
   its measures (the numbers), and which dimensions carry code lists.
2. **Data** — the observations, with coded values resolved to human labels
   using that structure.

> **Mnemonic: «LINDAS speaks in postcodes, not place names.»** An observation
> says region `1805`; the server turns that into «Alpennordhang» for you.

**Both steps happen inside `query_cube_observations`.** It fetches the
structure itself, so a caller does not have to call `get_cube_structure`
first to get readable rows — doing so only repeats the cube-metadata and
dimension queries. `get_cube_structure` is the tool for finding out what a
cube *contains* (dimension names, key vs. measure, licence) and for writing a
`run_sparql` query against it. It reports only whether a dimension has a code
list, not the entries, so it is not a decoding aid either.

---

## Architecture

```
                 ┌──────────────────────────────┐
                 │      MCP Host (Claude)       │
                 └───────────────┬──────────────┘
                                 │ stdio | streamable-http
                 ┌───────────────▼──────────────┐
                 │          lindas-mcp          │
                 │  ┌────────────────────────┐  │
                 │  │ server.py  (7 tools)   │  │  talks only to cube.py
                 │  ├────────────────────────┤  │
                 │  │ lindas/cube.py         │  │  ← vocabulary guardrail,
                 │  │                        │  │    two-phase access,
                 │  │                        │  │    code→label resolution
                 │  ├────────────────────────┤  │
                 │  │ lindas/queries.py      │  │  SPARQL templates,
                 │  │                        │  │    all anchored on a class
                 │  ├────────────────────────┤  │
                 │  │ lindas/client.py       │  │  raw SPARQL over HTTP,
                 │  │                        │  │    knows nothing of cubes
                 │  └────────────────────────┘  │
                 └───────────────┬──────────────┘
                                 │ HTTPS, no auth
                 ┌───────────────▼──────────────┐
                 │  lindas.admin.ch/query       │
                 │  SPARQL 1.1 · ~2000 cubes    │
                 └──────────────────────────────┘
```

The `lindas/` package is deliberately layered so it can be lifted into other
LINDAS-backed servers unchanged. `client.py` knows only HTTP and SPARQL;
`cube.py` knows the cube.link vocabulary; the tools know only `cube.py`. Raw
SPARQL never reaches the agent except through the guarded `run_sparql` escape
hatch.

### Architecture decision

**Architecture A (live SPARQL only), with a strict vocabulary guardrail.**

Verified live on 2026-07-21:
- The endpoint is stable, needs no authentication, and returns a clean HTTP 400
  with a diagnostic on malformed queries.
- Blind scans (`SELECT *`, `COUNT(*)` over the whole store) time out at
  60–90 s; the same question anchored on `?x a cube:Cube` answers in ~2 s.

Consequences, baked into the tools:
- Every query template is anchored on a known class. No unbounded scans.
- Two-phase access is enforced; the agent never sees raw codes.
- `run_sparql` is capped at 500 rows and 30 s and marked as advanced.
- The client timeout sits at 45 s, in front of the store's own 60–90 s abort.

Full probe report: [`docs/probe-lindas.md`](docs/probe-lindas.md).

---

## Tools

| Tool | Purpose |
|---|---|
| `search_cubes` | Find cubes by topic. Entry point. Deduplicates versions. |
| `get_cube_structure` | Phase 1: dimensions, measures, licence. |
| `query_cube_observations` | Phase 2: data points with codes resolved to labels. |
| `list_publishers` | Federal bodies publishing cubes, with counts. |
| `resolve_municipality` | Name ↔ URI ↔ BFS number — the portfolio join key. |
| `run_sparql` | Advanced escape hatch. Capped, guarded. |
| `api_status` | Reachability check with cube count. |

All tools are annotated `readOnlyHint: true`.

### Reading a `search_cubes` result

`returned` is a count of what came back, not a statement about what exists. Two
fields say how complete the answer is:

| Field | Meaning |
|---|---|
| `truncated` | `false` — every match is in `cubes`. `true` — there is more, or there may be more and the server could not rule it out. |
| `total_matched` | The exact total when one is available on the same unit as `returned`, `null` when no comparable number exists. |

**Check `truncated` before concluding anything.** On `true`, do not report the
result as complete and do not answer "there are N cubes about X" from
`returned`. Widen in this order: raise `limit` (up to 100); if it is still
truncated at 100, narrow with `creator_uri` from `list_publishers` and ask one
federal body at a time; use `latest_only=False` only when you actually want the
version history, because it widens the result rather than escaping the cut.

**`total_matched` is `null` more often than you might expect, and on purpose.**
With `latest_only=true` (the default) the count LINDAS can answer cheaply counts
cube *versions*, while the tool returns version-collapsed cubes. Measured on
2026-09-20 with German labels: «wald» matches 127 published versions that
collapse to 35 logical cubes, «energie» 33 to 13. A `total_matched` of 127 next
to a `returned` of 20 would claim 107 missing cubes where at most 15 exist to
find — so the field says `null`, which is true, instead of a number that is not.
`truncated` stays reliable there and is the field to act on.

Where the server has seen every matching row — which is the common case, because
it fetches one row beyond what it needs — `total_matched` is exact in both
branches, and `truncated` is derived from it rather than from the fetch limit.

---

## Installation

```bash
uvx lindas-mcp
```

### Claude Desktop

```json
{
  "mcpServers": {
    "lindas": {
      "command": "uvx",
      "args": ["lindas-mcp"]
    }
  }
}
```

### Remote deployment

```bash
LINDAS_MCP_TRANSPORT=streamable-http PORT=8000 lindas-mcp
```

`LINDAS_MCP_TRANSPORT` accepts `stdio` (default), `streamable-http` or `sse`.
**The transport decides the path**: `streamable-http` serves `/mcp`, `sse`
serves `/sse`. Anything else falls through to stdio, which opens no port at
all — in a container that surfaces only as a failing health check.
Both HTTP transports bind to `HOST`, **default `127.0.0.1`**;
set `HOST=0.0.0.0` explicitly to expose it (only behind a reverse proxy).
`LOG_LEVEL` tunes the JSON stderr logs.

#### Hosting it as a remote connector

**The connector URL is `https://<host>/mcp`.** The path is not configurable —
it comes from the transport, and `streamable-http` is the one a current client
expects. `sse` and its `/sse` path are the specification's superseded transport;
nothing was removed and they still serve, but a new connector should not be
pointed at them.

A hosted deployment — Railway, Fly, a container behind any reverse proxy — needs
three variables, and the third is the one a deployment inherits wrongly because
nothing fails loudly without it:

| Variable | Hosted value | If unset |
|---|---|---|
| `LINDAS_MCP_TRANSPORT` | `streamable-http` | Falls through to stdio: the process starts, opens no port, and surfaces only as a failing health check. The container image already sets it. |
| `HOST` | `0.0.0.0` | Binds loopback only, so the published port reaches nothing. The image sets it deliberately (SEC-016). |
| `LINDAS_MCP_ALLOWED_HOSTS` | the public hostname | **`Host` validation is switched off entirely** — see below. |

**`LINDAS_MCP_ALLOWED_HOSTS` is a comma-separated list of hostnames, without
scheme and without port**: `lindas-mcp.example.ch,alias.example.ch`, not
`https://lindas-mcp.example.ch:443`. The value is matched literally against the
incoming `Host` header, and behind TLS on port 443 that header carries no port.
Loopback forms are added automatically, so the container health check keeps
working.

It fails in two opposite directions:

- **Unset on a non-loopback bind: the protection is off altogether.** No
  hostname is derivable in that situation — the server is reached under a
  service or public DNS name this process does not know, and a guessed list
  would answer every real request with 421. So no allow-list is installed at
  all and the `Host` header is never checked, which is the SDK's own default.
  The only sign is a startup warning, `dns_rebinding_protection_off`.
- **Set to the wrong name: every real request gets HTTP 421.** The match is
  exact and port-precise — `mcp.example.ch` does not cover
  `Host: mcp.example.ch:8443`. If the proxy forwards a non-default port, name
  both forms.

`ALLOWED_ORIGINS` is a separate question and concerns **browser** clients only.
It is the CORS origin list, comma-separated, and **unset means no browser client
is permitted at all** — that is the default. A client that is not a browser
sends no `Origin` and is unaffected. `*` is still accepted and logs a warning.
One detail worth knowing if you do serve browsers: the origins derived from
`LINDAS_MCP_ALLOWED_HOSTS` are the `http://` ones, so an `https://` browser
origin has to be named in `ALLOWED_ORIGINS` yourself.

### Docker

```bash
docker compose up --build          # binds 0.0.0.0 inside the container, publishes :8000
```

The image runs as a non-root user, read-only, with resource limits and a
TCP health check (see [`Dockerfile`](Dockerfile) and [`compose.yaml`](compose.yaml)).

---

## Join keys

LINDAS is a connector layer, and two of its identifiers make it composable with
the rest of the portfolio:

| Key | Where | Joins to |
|---|---|---|
| BFS commune number | `resolve_municipality` → `bfs_number` | swiss-statistics-mcp, zurich-opendata-mcp |
| Fedlex URI | cube `licence` field | [fedlex-mcp](https://github.com/malkreide/fedlex-mcp) |

The Fedlex link is the quiet surprise: many cubes declare their licence as a
legal-basis URI (`fedlex.data.admin.ch/eli/cc/...`), so you can go from a data
point straight to the law that governs it.

---

## Known limitations

Verified live on 2026-07-21.

1. **Broad SPARQL times out.** The store aborts unanchored scans at 60–90 s.
   The guarded tools avoid this; `run_sparql` warns about it and caps runtime.
2. **Observations are coded.** Dimension values are URIs, not labels. The server
   resolves them via each dimension's code list, but resolution costs one extra
   query per coded dimension. Set `resolve_labels=False` to skip it.
3. **No server-side observation filtering by arbitrary value.** LINDAS has no
   cheap way to filter observations by a dimension value inside a cube, so
   `query_cube_observations` reads the first N observations. Analytical slicing
   belongs in `run_sparql`.
4. **Licences vary per cube** and are declared as `dcterms:license`, frequently
   a Fedlex URI rather than a plain name. Always surface the `licence` field.
5. **Version handling is heuristic.** `search_cubes` deduplicates by stripping
   the version suffix from the cube URI and keeping the highest `schema:version`
   among published cubes. Unusual URI shapes may not collapse cleanly; use
   `latest_only=False` to inspect every version. The same heuristic is why
   `total_matched` can be `null`: it is a URI-shape guess in Python, and no cheap
   SPARQL count expresses it, so restating it in a query would put the same guess
   in a second place where it can drift.

---

## MCP Protocol Version

This server speaks **two protocol eras** over the same endpoint. The client's
first request on a connection decides which one applies; a later claim from the
other era is refused.

| Era | Revision | Who reaches it |
|---|---|---|
| `initialize` handshake | `2024-11-05` … **`2025-11-25`** | What today's clients speak. The server answers with the revision asked for, or with the `2025-11-25` ceiling when the request asks for something newer. |
| Per-request envelope | **`2026-07-28`** | A request carrying the `2026-07-28` `_meta` envelope opens a modern connection. |

Both revisions are pinned in
[`tests/test_protocol_version.py`](tests/test_protocol_version.py) and asserted
against the installed SDK, so a Dependabot bump of `mcp` cannot move either one
silently. The handshake ceiling is measured against a live `initialize` through
the assembled ASGI stack, not read off a constant name.

Note that the SDK's `LATEST_PROTOCOL_VERSION` is an alias for the **modern**
era, not for the handshake era — pinning against it alone would leave the era
that current clients actually negotiate free to drift.

### What `2026-07-28` changes here

The modern era has no `initialize` handshake, and therefore no handshake result
in which a client learns who it is talking to. Three consequences are served
explicitly rather than left at the SDK's defaults:

| Surface | Behaviour |
|---|---|
| `serverInfo` | Stamped into `_meta` on every response and into `server/discover`. Name, title, version, description and website URL are resolved from the installed distribution's metadata, never written by hand. `MCPServer` defaults `version` to `""` and substitutes nothing, so an unset version is a required field that says nothing. |
| `instructions` | Returned by `server/discover` — the only orientation channel a modern client has. It names the entry point, says that `query_cube_observations` resolves labels on its own, and says what `get_cube_structure` is actually for. |
| Log delivery | `logging/setLevel` is gone (SEP-2577); a client opts in per request via the reserved `_meta` key `io.modelcontextprotocol/logLevel`. Without it the server sends nothing; with `debug` it sends one `notifications/message` per tool call on that request's stream. |
| `tools/list`, `server/discover` | Carry `ttlMs` 300000 and `cacheScope` `public` (SEP-2549). |

All of it is measured through the assembled stack in
[`tests/test_spec_2026_07_28.py`](tests/test_spec_2026_07_28.py) — both eras,
both transports, and both branches of the log opt-in. The tool contract itself
is guarded independently by `tool-definitions.lock.json` (SEC-022), and the
modern era is asserted to serve exactly the tools listed there, so the two eras
cannot drift into two different servers behind one address.

**Update policy.** When the gate fails, do not edit the constant blindly: read
the spec changelog between the two revisions, verify the server still behaves,
then move the constant, this section, `README.de.md` and
[`CHANGELOG.md`](CHANGELOG.md) together. SDK upgrades are a reviewed change for
the same reason: any protocol-affecting bump is called out in
[`CHANGELOG.md`](CHANGELOG.md).

---

## Testing

```bash
PYTHONPATH=src pytest tests/ -m "not live"   # offline, used in CI
PYTHONPATH=src pytest tests/ -m "live"       # hits the real endpoint
python -m ruff check src tests
```

The live tests earn their place: the `observationSet` indirection (a cube's
observations hang off `cube:observationSet`, never directly off the cube) is a
structural assumption that a mock cannot validate. It is covered by a live test.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the ground rules (read-only, one
egress host, anchored queries) and the local dev loop. Further reading:
[`EXAMPLES.md`](EXAMPLES.md) for use cases by audience with the tool-selection
table, [`docs/roadmap.md`](docs/roadmap.md) for the project phase, and
[`PUBLISHING.md`](PUBLISHING.md) for the PyPI / MCP Registry release process.

---

## Security

See [`SECURITY.md`](SECURITY.md) for the security posture and how to report a
vulnerability.

---

## License

MIT License — see [LICENSE](LICENSE). The LINDAS data remains subject to the
licence each publisher declares on the cube.

---

## Author

**Hayal Oezkan** · [github.com/malkreide](https://github.com/malkreide)

---

## Credits & related projects

- Data: [LINDAS Linked Data Service](https://lindas.admin.ch), Swiss Federal Archives
- Vocabulary: [cube.link](https://cube.link)
- Visualisation frontend on the same cubes: [visualize.admin.ch](https://visualize.admin.ch)
- Source discovery inspired by [rnckp/awesome-ogd-switzerland](https://github.com/rnckp/awesome-ogd-switzerland)
- Portfolio: [swiss-public-data-mcp](https://github.com/malkreide/swiss-public-data-mcp)

Licence: MIT. The cube data remains subject to the licence each publisher declares.

---

## MCP Registry

Ownership marker used by the [MCP Registry](https://registry.modelcontextprotocol.io)
to link this PyPI package to the GitHub namespace:

```
mcp-name: io.github.malkreide/lindas-mcp
```
