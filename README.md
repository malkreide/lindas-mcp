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

---

## The two-phase access pattern

LINDAS cubes are self-describing but coded. Reading them well means two steps,
which this server enforces:

1. **Structure first** — `get_cube_structure` reads the cube's SHACL shape: its
   dimensions (filterable axes), its measures (the numbers), and which
   dimensions carry code lists.
2. **Data second** — `query_cube_observations` reads the observations and
   resolves coded values to human labels using the structure from step 1.

> **Mnemonic: «LINDAS speaks in postcodes, not place names.»** An observation
> says region `1805`; the server turns that into «Alpennordhang» for you.

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
LINDAS_MCP_TRANSPORT=sse PORT=8000 lindas-mcp
```

`LINDAS_MCP_TRANSPORT` accepts `stdio` (default), `sse` or `streamable-http`.

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
   `latest_only=False` to inspect every version.

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

## Credits & related projects

- Data: [LINDAS Linked Data Service](https://lindas.admin.ch), Swiss Federal Archives
- Vocabulary: [cube.link](https://cube.link)
- Visualisation frontend on the same cubes: [visualize.admin.ch](https://visualize.admin.ch)
- Source discovery inspired by [rnckp/awesome-ogd-switzerland](https://github.com/rnckp/awesome-ogd-switzerland)
- Portfolio: [swiss-public-data-mcp](https://github.com/malkreide/swiss-public-data-mcp)

Licence: MIT. The cube data remains subject to the licence each publisher declares.
