# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Der Backoff-Schlaf wird ueber einen Modul-Alias gepatcht, nicht ueber
  `asyncio.sleep`.** Die Tests nullten die Wartezeit mit
  `monkeypatch.setattr(<modul>.asyncio, "sleep", ...)`. Das liest sich lokal,
  ersetzt `sleep` aber auf dem geteilten Modulobjekt — fuer httpx, respx,
  pytest-asyncio und jeden anderen Importeur im Prozess. Das Modul legt die
  Naht jetzt als `_sleep = asyncio.sleep` offen; gepatcht wird diese.
  `test_der_retry_geht_ueber_den_alias` haelt sie: umgeht der Retry den Alias,
  faellt der Test in Sekundenbruchteilen. Ohne ihn fiel gar nichts — die Suite
  wurde nur ein Vielfaches langsamer, und eine laengere Laufzeit ist kein
  Signal, das jemand liest.

### Behoben

- **Der 20-Sekunden-Deckel war keine Grenze.** Gedeckelt wurde *vor* dem
  Jittern, also wurde ein auf `MAX_DELAY_S` gedeckelter Wert anschliessend mit
  bis zu 1.5 multipliziert: exponentielle Wartezeiten bis 30 s,
  `Retry-After`-Wartezeiten bis 25 s. Neu wird nach dem Jittern gedeckelt.

- **Das Gesamtbudget war nicht garantiert.** `httpx` wendet sein Timeout pro
  Operation an, und das Read-Timeout beginnt mit jedem Chunk von vorn — eine
  langsam troepfelnde Antwort konnte das Budget ueberdauern, ohne dass ein
  einzelner Read ablief. Neu liegt eine `asyncio.wait_for`-Deadline um die
  Anfrage. (`asyncio.timeout` laese sich besser, kam aber erst in 3.11; dieses
  Paket unterstuetzt weiterhin 3.10.)

  Beide Befunde stammen aus einem Codex-Review an `parlament-mcp#35`. Der Test
  zur Deadline haelt die *echte* `asyncio.sleep` beim Import fest und laeuft
  ohne die Fake-Uhr der uebrigen Budget-Tests: Eine Zusicherung ueber echte Zeit
  laesst sich nicht mit einer ausgepatchten Uhr widerlegen.


### Added

- **`Retry-After` wird gelesen und schlaegt die eigene Backoff-Kurve** (ARCH-014).
  Bei 429 und 503 sagt der Store im Header, wann er wieder mag — als
  Sekundenzahl oder HTTP-Datum; beide Formen kommen vor, beide werden gelesen
  (RFC 9110 §10.2.3). Wer stattdessen weiter seine Kurve faehrt, ignoriert eine
  ausdrueckliche Angabe. Ein unbrauchbarer Header fuehrt zurueck auf die Kurve
  statt zum Absturz — auf dem Fehlerpfad darf eine kaputte Kopfzeile nicht das
  Letzte sein, woran der Client stirbt.

- **Backoff ist gestreut (Jitter).** `2**attempt` war deterministisch: Faellt
  LINDAS aus, waehrend mehrere Clients es abfragen, retryen alle im Gleichtakt,
  und die Last kommt als Welle zurueck — genau wenn der Store sich erholt.
  Exponentielle Wartezeiten landen jetzt in `[0.5x, 1.5x]`. Auf einem
  `Retry-After` ist die Streuung einseitig (`[1.0x, 1.25x]`): spaeter ist
  hoeflich, frueher waere die Missachtung derselben Angabe, die man gerade
  gelesen hat.

- **Deckel von 20 s auf jede einzelne Wartezeit** — gegen die unbegrenzt
  wachsende Leiter und gegen ein `Retry-After`, das der Store senden darf, das
  man aber nicht absitzen muss.

- **Gesamtbudget von 45 s ueber den ganzen Aufruf** (ARCH-014). Eine Anzahl
  Versuche ist keine Grenze: Vier Versuche a 45 s plus Backoff sind ueber drei
  Minuten, und `MAX_ATTEMPTS = 4` sagt das nirgends. Geprueft wird vor jedem
  Versuch: Eine Wartezeit, die das Budget ueberdauern wuerde, wird nicht mehr
  angetreten, und das Timeout einer einzelnen Query ist auf die verbleibende
  Zeit geklemmt. Ein explizites `timeout_s` bleibt gueltig, wenn es enger ist —
  es gewinnt der kleinere der beiden Werte.

  **Der Wert liegt bewusst ueber dem MCP-Client-Default.** Das Python-SDK setzt
  `MCP_DEFAULT_TIMEOUT = 30.0`, und die Schwester-Server im Portfolio
  (`swiss-efv-mcp`, `termdat-mcp`) bleiben mit 25 s darunter. LINDAS ist die
  Ausnahme mit Absicht: Es liefert SPARQL, keinen festen Dump. Der Store bricht
  teure Queries selbst erst bei 60-90 s ab, und `TIMEOUT_S = 45.0` existiert
  genau, um davor zu schneiden. Ein Budget unter 30 s wuerde legitime Queries
  abwuergen, die heute durchkommen — eine echte Faehigkeit gegen die Konformitaet
  mit einem Default eingetauscht.

  Die Folge ist angenommen, nicht uebersehen: Ein Aufrufer mit SDK-Default kann
  aufgeben, bevor eine langsame Query zurueckkommt. Die bindende Grenze ist hier
  das Abbruchfenster des Stores, und 45 s bleiben darin. Ein Test haelt diese
  Abweichung fest — er prueft, dass das Budget **ueber** dem SDK-Default liegt,
  damit sie eine dokumentierte Entscheidung bleibt und eine spaetere stille
  Verengung laut scheitert.

  Log und Meldung nennen neu, **welche** Grenze gegriffen hat: «all 4 attempts
  used» und «45s budget spent» verlangen verschiedene Antworten.

## [0.2.1] - 2026-08-02

### Fixed

- **`structlog` carried no upper bound, and the index already serves a major past
  the floor.** The declared range was `structlog>=24.1`; PyPI has been serving
  `26.1.0`. The artefact does not change — the resolver's answer to the next
  fresh install does, and that is exactly how `swiss-energy-mcp` 0.3.3 became
  uninstallable when `mcp` 2.0.0 removed the module it imported.

  Now `structlog>=24.1,<27`. The bound is measured rather than guessed: this package
  installs and imports against `structlog 26.1.0` today, so the cap admits what
  demonstrably works and stops only the next, unknown major.

A dependency range only reaches users through a new release, hence the
version bump. No code changed.

## [0.2.0] — 2026-08-02

This release exists so that a repair reaches the people running the server:
**the published `0.1.0` cannot be installed any more.** It declares `mcp` with
no upper bound, and `mcp` 2.0.0 removed `mcp.server.fastmcp` — so a fresh
`pip install lindas-mcp` resolves to 2.0.0 and the console script dies on
startup with `ModuleNotFoundError`. Measured against the real artefact in an
empty venv, cold and warm interpreter alike.

The repository has carried the fix since the 2.x migration was merged; it was
simply never released, and `main` kept the same version number as the broken
artefact — so nothing contradicted it.

### Changed (breaking)

- **Migrated to the `mcp` Python SDK 2.x.** The server API moved from
  `mcp.server.fastmcp` to `mcp.server.mcpserver` with no compatibility shim,
  and the dependency is now `mcp>=2.0.0,<3`. The tool surface is unchanged —
  what breaks is embedding this server's Python API and the dependency floor.
  Anyone who must stay on `mcp` 1.x should stay on 0.1.0, and pin an upper
  bound themselves, because the published 0.1.0 has none.

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
