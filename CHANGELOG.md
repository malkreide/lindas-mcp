# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
