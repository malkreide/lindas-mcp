# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **`search_cubes` sagt jetzt, ob die Antwort vollständig ist.** Zurück kamen
  bisher nur `returned` Treffer — und damit konnte ein Client «das ist alles»
  nicht von «das ist Seite eins» unterscheiden. Wer es nicht unterscheiden kann,
  hört bei der Seite auf, die er bekommen hat, und antwortet «es gibt N Cubes zu
  X» aus einer Zahl, die bloss sein eigenes Limit ist.

  Neu sind zwei Felder: **`truncated: bool`** und
  **`total_matched: int | None`**.

  `truncated` ist das tragende Feld und irrt absichtlich nach oben. `false`
  heisst: alles, was passt, steht in `cubes`. `true` heisst: es gibt mehr — oder
  es kann mehr geben und die Suchschicht konnte es nicht ausschliessen. Ein
  falsches `true` kostet eine weitere Abfrage, ein falsches `false` kostet dem
  Aufrufer den Rest des Ergebnisses, ohne es zu sagen. Die Tool-Beschreibung
  nennt den Ausweg in der richtigen Reihenfolge: `limit` erhöhen (bis 100), dann
  über `creator_uri` aus `list_publishers` verengen statt zu blättern — und
  `latest_only=False` nur für die Versionshistorie, weil es verbreitert und
  gerade kein Ausweg aus der Kürzung ist.

  **`total_matched` ist bewusst nullable, und das ist der eigentliche Entwurf.**
  Gemessen live gegen `lindas.admin.ch` am 20.9.2026, deutsche Labels:

  | Begriff | `COUNT(DISTINCT ?cube)` | logische Cubes nach Dedup |
  |---|---|---|
  | `wald` | 127 | 35 |
  | `energie` | 33 | 13 |
  | `e` | 1528 | ≥ 287 (selbst gedeckelt) |

  Eine Zählabfrage ist schnell genug — 230 bis 932 ms über vier Begriffe, und
  die beiden langsamsten Messungen waren je die erste Anfrage eines Laufs, also
  TLS-Aufbau. Der Engpass ist nicht die Zeit, sondern die **Vergleichbarkeit**:
  Der COUNT zählt Cube-*Versionen*, das Tool liefert im Standardfall
  versions-kollabierte Cubes. Ein `total_matched` von 127 neben einem `returned`
  von 20 behauptet 107 fehlende Cubes, wo höchstens 15 zu finden sind.

  Darum drei Wege in dieser Reihenfolge: (1) um eine Zeile überfetchen — kommen
  weniger Zeilen zurück als angefordert, hat die Pipeline jede passende Zeile
  gesehen und das Total ist gratis exakt, auf der richtigen Einheit, in beiden
  Zweigen; (2) gedeckelt und `latest_only=False` — hier sind Zeilen Versionen,
  also zählt eine zweite Abfrage dasselbe und antwortet exakt, mit eigenem
  Budget von 8 s, und ein Fehlschlag kostet das Total und nicht die Treffer;
  (3) gedeckelt und `latest_only=True` — `total_matched` bleibt `null`, weil
  keine billige Abfrage die URI-Heuristik aus `_base_cube_uri` ausdrückt und ein
  Nachbau in SPARQL dieselbe Vermutung an einer zweiten Stelle führen würde, wo
  sie driften kann.

  **Ein zweiter Messbefund entschied eine einzelne Zeile.** Acht Cubes im Store
  tragen gar kein `schema:creativeWorkStatus`. Die Suchschicht behält sie
  (`or "status" not in r`), ein strenges
  `FILTER(STRENDS(STR(?status), "Published"))` wirft sie weg — für `e` gemessen
  1520 gegen 1528. Die Zählvorlage spiegelt den Filter deshalb mit
  `!BOUND(?status) ||`; ohne das wäre jedes Total still um genau diese acht kurz,
  und die Zählung hätte der Auslassung auch noch zugestimmt.

  Bekannte Grenze, dokumentiert statt angenommen: Der COUNT zählt
  `DISTINCT ?cube`, die Trefferliste zählt Zeilen. Auf den drei geprüften
  Begriffen sind beide deckungsgleich (127/127, 45/45, 500/500 distinct), aber
  `search_cubes` projiziert `?creator` und `?version` über `OPTIONAL` — ein Cube
  mit zwei Creators in derselben Sprache würde die beiden Zahlen trennen.

  Gegenprobe über elf Neutralisierungen gefahren. Eine war beim ersten Durchgang
  grün: das `+ 1` der Überfetchung liess sich entfernen, ohne dass irgendetwas
  rot wurde, weil die Mocks eine feste Zeilenzahl liefern, egal welches `LIMIT`
  die Abfrage nennt. Das ist genau der Test, der grün bleibt, wenn man die
  Implementierung entfernt — dafür gibt es jetzt zwei eigene Tests, genau `limit`
  Treffer und eine Zeile unter dem Deckel. Der Live-Test kalibriert sich selbst:
  Er liest das Total aus dem Store und leitet seine Limits daraus ab, statt 127
  zu pinnen, und hält zusätzlich die Prämisse des Entwurfs fest — kollabierte
  Cubes müssen weniger sein als Versionen.

  `tool-definitions.lock.json` bleibt unverändert: Die Argumentfläche ändert
  sich nicht, beide Felder sind Rückgabefelder, und `_stable_signature` erfasst
  ausdrücklich nur Namen und `required`.

### Changed

- **Die Connector-URL und `LINDAS_MCP_ALLOWED_HOSTS` stehen jetzt in beiden
  READMEs.** Gemeldet aus einem Railway-Deployment. Die Variable existierte nur
  in `src/` und `tests/` — und das ist die Kombination, die ein Hosting still
  falsch erbt: Bei einem Non-Loopback-Bind ohne Allow-List gibt
  `build_transport_security()` `None` zurück, das SDK lässt den
  DNS-Rebinding-Schutz dann **ganz** aus, und das einzige Anzeichen ist die
  Startwarnung `dns_rebinding_protection_off`. Wer die Variable nicht kennt,
  kann sie nicht setzen.

  Dokumentiert sind jetzt in beiden Sprachen die Connector-URL
  `https://<host>/mcp`, die drei Variablen eines gehosteten Deployments als
  Tabelle mit der Folge je fehlender Variable, die Schreibweise der Allow-List
  — kommagetrennt, ohne Schema und ohne Port, weil der Wert wörtlich gegen die
  `Host`-Kopfzeile geht und die hinter TLS auf 443 keinen Port trägt — und beide
  Fehlrichtungen: nicht gesetzt heisst Prüfung aus, falsch gesetzt heisst
  HTTP 421 auf jede echte Anfrage, portgenau. Dazu, dass `ALLOWED_ORIGINS` eine
  andere Frage ist und nur Browser betrifft, samt dem Detail, dass die aus der
  Allow-List abgeleiteten Origins `http://`-Varianten sind.

  Kein Code geändert; jede Aussage hängt an einem bestehenden Test
  (`test_foreign_host_is_rejected`, `test_right_host_wrong_port_is_rejected`,
  `test_non_local_bind_without_allowlist_stays_off`).

- **BRECHEND für bestehende HTTP-Deployments: das Image fährt jetzt
  `streamable-http` statt `sse`.** Damit wechselt der Endpunkt-Pfad von `/sse`
  auf **`/mcp`** — wer den Container hinter einem Reverse-Proxy oder in einer
  Client-Konfiguration auf `/sse` verdrahtet hat, muss den Pfad nachziehen.
  `compose.yaml` zieht mit, damit `docker compose up` und ein nacktes
  `docker run` nicht auf verschiedenen Pfaden bedienen.

  **Wer beim alten Transport bleiben will, setzt `LINDAS_MCP_TRANSPORT=sse`**
  als Umgebungsvariable; entfernt wurde nichts, nur der Standard gedreht. SSE
  ist der abgelöste Transport der Spezifikation, `streamable-http` der aktuelle
  — der Standard zeigt jetzt dorthin, wohin neue Clients ohnehin gehen.

  Beide Pfade stehen ab jetzt in den READMEs. Bisher stand dort keiner, obwohl
  der Transport ihn bestimmt.

### Fixed

- **Jeder HTTP-Start starb, bevor uvicorn erreicht wurde.** `main()` setzte
  `mcp.settings.host` und `.port`; in mcp 2.x hat `Settings` keines von beiden,
  also brach pydantic mit `ValueError: "Settings" object has no field "host"`
  ab — auf einem Container-Host als Neustartschleife. Gemeldet aus einem
  Railway-Deployment.

  Beide Werte erreichen ihr Ziel ohne `settings`: `host` als Keyword-Argument
  der App-Factory, `port` als `uvicorn.run`-Argument. Dieselbe Entfernung hatte
  `transport_security` getroffen, dort war die Zeile schon weg — die zwei
  Schwesterzeilen eine Ebene höher beim Aufrufer blieben stehen, weil kein Test
  `main()` aufrief. `tests/test_entry_point.py` fährt den Startpfad jetzt.

  **Ein Tippfehler in `LINDAS_MCP_TRANSPORT` bleibt trotzdem still**: `main()`
  fällt auf stdio durch, der Prozess startet, öffnet keinen Port und fällt erst
  am Healthcheck auf. Dass der Wert des Images kein solcher Tippfehler ist,
  prüft jetzt ein Gate gegen `HTTP_TRANSPORTS`.

- **Der Startbefehl lud das Modul zweimal.** `CMD ["python", "-m",
  "lindas_mcp.server"]` zusammen mit einem `__init__.py`, das `.server`
  importiert, hinterliess zwei verschiedene `MCPServer`-Objekte im Prozess und
  die `RuntimeWarning` in jedem Container-Log. Jetzt `CMD ["lindas-mcp"]`, der
  Konsolen-Entry-Point, der genau einmal importiert.

## [0.3.0] - 2026-09-19

### Changed

- **BRECHEND: Browser-Origins sind jetzt fail-closed.** `allow_origins` stand
  standardmässig auf `*` —
  jede Website im Internet konnte diesen Server aus dem Browser eines
  Besuchers aufrufen. Gemessen vorher:
  `Origin: https://boesartig.example` bekam `200` mit
  `Access-Control-Allow-Origin: *`.

  Die Origins kommen jetzt aus `ALLOWED_ORIGINS` (kommagetrennt) und
  sind **standardmässig leer** — kein Browser-Client wird zugelassen. Wer
  Browser-Clients will, nennt die Origins; niemand erbt eine Freizügigkeit, die
  er nicht gewählt hat.

  `*` ist weiterhin erreichbar, aber nicht mehr stillschweigend: es muss
  ausdrücklich gesetzt werden und schreibt eine Warnung ins Log. Eine
  Verengung des Standards ist nicht dasselbe wie das Entfernen der Option.

  **Wer den bisherigen Zustand behalten will, setzt `ALLOWED_ORIGINS=*`.**
  stdio- und andere Nicht-Browser-Clients sind unberührt — CORS betrifft nur
  Browser.

### Fixed

- **`serverInfo` meldete eine leere Version — in beiden Ären, über beide
  Transporte.** `MCPServer` deckt `version` mit `""` vor und setzt nichts
  eigenes ein («An unversioned server reports an empty `version`; the SDK never
  substitutes its own»). Der Server übergab nichts, also trug jede Antwort
  `{"name": "lindas-mcp", "version": ""}` — gemessen am `initialize`-Ergebnis
  der Handshake-Ära ebenso wie am `_meta`-Stempel jeder modernen Antwort.

  In `Implementation` ist `version` ein **Pflichtfeld**; der leere String
  erfüllt es der Form nach und sagt nichts. In der modernen Ära wiegt das
  schwerer als in der alten: dort gibt es keinen `initialize`-Handshake und
  damit kein Handshake-Ergebnis — der Stempel ist die einzige Stelle, an der
  ein Client erfährt, welche Fassung ihm antwortet.

  Gesetzt werden jetzt `version`, `title`, `description` und `websiteUrl`, alle
  aus den Metadaten der installierten Distribution (`_version`), nicht aus
  Literalen: `check_version_sync.py` verbietet eine hartkodierte Version in
  `src/` ausdrücklich, und für Zusammenfassung und URL gilt derselbe Grund, nur
  ohne Gate. `icons` bleibt leer — dafür bräuchte es eine gehostete Grafik, und
  eine erfundene URL wäre schlechter als das Feld wegzulassen.

- **README.md nannte den Protokollstand zweimal, und die zweite Fassung war
  falsch.** Unter `## MCP protocol version` (klein geschrieben, am Dateiende)
  stand `mcp>=1.28.1`, während `pyproject.toml` seit dem 2.x-Umstieg auf
  `mcp>=2.0.0,<3` steht. Zwei Abschnitte zum selben Gegenstand, einer veraltet
  — und der veraltete stand weiter unten, also näher an dem, was jemand beim
  Überfliegen zuletzt liest. Aufgelöst in **einen** Abschnitt; der Hinweis auf
  `tool-definitions.lock.json` (SEC-022) ist mitgewandert und nicht verloren.

- **Jeder HTTP-Transport starb beim Start.** `_run_http` setzte
  `mcp.settings.transport_security = security` — die Form vor 2.x. In `mcp` 2.x
  gibt es das Feld nicht, pydantic wirft `ValueError: "Settings" object has no
  field "transport_security"`, und zwar bevor uvicorn erreicht wurde. Die
  Transport-Sicherheit ist jetzt ein Schlüsselwort-Argument von
  `build_http_app`. Ohne sie kam ein fremder `Host` durch die Prüfung (400
  statt 421); der Test hält diesen Unterschied fest, statt bloss zu belegen,
  dass die Funktion das Argument entgegennimmt.

- **`allow_headers` stand auf `["*", "Mcp-Session-Id"]`,** und die Wildcard
  gewann: Starlette schaltet damit auf `allow_all_headers` und spiegelt im
  Preflight zurück, was der Browser ankündigt. Die Liste nennt jetzt
  `Content-Type`, die drei Routing-Header der Spec `2026-07-28`,
  `Mcp-Session-Id` und `Last-Event-ID`. Letzterer setzt einen abgerissenen
  SSE-Strom fort und war unter der Wildcard nie geprüft.

  Der Standard von `ALLOWED_ORIGINS` bleibt `*`. Das ist eine eigene
  Entscheidung mit eigenen Folgen für bestehende Clients.

### Added

- **`instructions` für die moderne Ära.** `server/discover` gab sie leer
  zurück. In der Handshake-Ära ist das verschmerzbar — dort liefert
  `initialize` eine Antwort, in der ein Client Kontext findet. In der modernen
  Ära gibt es dieses Ergebnis nicht: `server/discover` ist der **einzige**
  Orientierungskanal. Leer gelassen erfährt ein moderner Client nirgends, dass
  der Zugriff zweiphasig ist, ruft `query_cube_observations` vor
  `get_cube_structure` und bekommt Codes zurück, die er nicht auflösen kann.
  Der Text nennt die Reihenfolge, die Timeout-Neigung des Stores und die
  BFS-Nummer als Join-Key ins Portfolio.

- **`tests/test_spec_2026_07_28.py` — die moderne Ära, gemessen statt
  dokumentiert.** Beide READMEs beschrieben den Pro-Request-Envelope, und kein
  Test fuhr ihn: wäre der moderne Pfad vollständig kaputt gewesen, wäre nichts
  rot geworden. `test_protocol_version.py` pinnt die Revisionen und fährt einen
  echten `initialize` — aber nur den.

  Gemessen wird jetzt durch den zusammengebauten Stack: `server/discover` mit
  `supportedVersions`, der `serverInfo`-Stempel gegen `__version__`, ein echter
  `tools/call` aus einer Aufzeichnung, die Werkzeuggleichheit beider Ären gegen
  `tool-definitions.lock.json`, der Envelope als Pflicht, die beiden
  Header-Mismatches, eine unbekannte Revision, `initialize` als auf dem
  modernen Pfad nicht erreichbar — und, weil dieser Server standardmässig über
  stdio läuft, derselbe Einstieg noch einmal als Unterprozess.

  Gegenprobe gefahren: `version` entfernt → drei Tests fallen (auch der
  stdio-Test), `instructions` entfernt → einer, die übrigen Identitätsfelder
  entfernt → einer, `ctx.debug` entfernt → einer.

- **Beide Zweige der Log-Anmeldung festgehalten.** Spec `2026-07-28` kehrt die
  Voreinstellung um: `logging/setLevel` ist weg (SEP-2577), stattdessen meldet
  sich der Client **pro Anfrage** über den reservierten `_meta`-Schlüssel
  `io.modelcontextprotocol/logLevel` an; ohne ihn darf der Server nichts
  senden.

  Das SDK markiert `ctx.debug` deshalb als veraltet, und die Warnung steht
  standardmässig im stderr — die Kategorie erbt von `UserWarning`, nicht von
  `DeprecationWarning`. Der naheliegende Schluss wäre, den Aufruf zu löschen.
  Er ist falsch: veraltet ist die *Fähigkeit*, nicht die Benachrichtigung.
  Gemessen, derselbe Aufruf zweimal über den modernen Pfad — ohne den
  Schlüssel `application/json` und keine `notifications/message`, mit
  `logLevel: "debug"` ein `text/event-stream` mit dem Eintrag darin. Wer die
  Warnung durch Löschen stillstellt, nimmt einem Client etwas weg, das die
  Zielrevision vorsieht und das er angefordert hat. Beide Richtungen stehen
  jetzt als Test; die Begründung steht im Docstring von `_log_call`.

- **Frischehinweise auf `tools/list` und `server/discover`** (SEP-2549, Spec
  `2026-07-28`): `ttlMs` 300000, `cacheScope` `public`. Das SDK setzt beides von
  sich aus auf «sofort veraltet, nie geteilt» — wer nichts übergibt, verhält
  sich also nicht neutral, sondern lässt jeden Client bei jeder Verbindung neu
  auflisten, für eine Liste, die beim Import feststeht und für jeden Aufrufer
  dieselbe ist. `prompts/list` und `resources/list` bleiben ungesetzt: dieser
  Server registriert weder das eine noch das andere.

- **Protokoll-Gate: beide Spec-Aeren gepinnt und geprueft**
  (`tests/test_protocol_version.py`). `mcp` 2.x bedient zwei Aeren ueber
  denselben Server — den `initialize`-Handshake, der bei `2025-11-25`
  deckelt, und den Pro-Request-Envelope, der `2026-07-28` erreicht.
  `LATEST_PROTOCOL_VERSION` ist ein Alias auf die **moderne** Aera; wer nur
  dagegen pinnt, laesst genau die Aera frei wandern, die heutige Clients
  aushandeln. Beide sind jetzt einzeln gepinnt, ein Dependabot-Bump von
  `mcp` kann keine davon still verschieben.

  Nachgemessen statt aus Konstantennamen geschlossen: ein echter `initialize`
  durch den zusammengebauten ASGI-Stack. Ein Client, der ueber den Handshake
  nach `2026-07-28` fragt, bekommt `2025-11-25` zurueck.

  Beide READMEs beschreiben die Aeren; ein Test haelt jede Sprache einzeln
  dagegen — im Portfolio sind EN und DE desselben Repos schon dreimal
  auseinandergelaufen, weil nur eine Fassung nachgezogen wurde.

### Fixed

- **Die Pruefsummen im Fixture-Nachweis waren Zierde.** `PROVENANCE.md` fuehrt
  je Datei einen SHA-256 — um genau einen Fall zu fangen: eine Aufzeichnung,
  die nach dem Lauf von Hand nachgebessert wurde. Eine korrigierte Antwort ist
  wieder eine erfundene, und von aussen ist ihr das nicht anzusehen.
  Nachgerechnet hat sie kein Test. `test_die_pruefsumme_im_nachweis_stimmt`
  tut es jetzt, ueber die Bytes auf der Platte statt ueber den Loader — genau
  die hat der Recorder gehasht.

- **Der Recorder startete auf Python 3.10 nicht.** `scripts/record_fixtures.py`
  schrieb `from datetime import UTC` — ein Alias, das es erst ab 3.11 gibt,
  während `requires-python` dieses Repos `>=3.10` sagt und die CI-Matrix 3.10
  fährt. Der Testteil derselben Änderung hatte es getroffen und wurde von der
  CI gemeldet; der Recorder nicht, weil ihn niemand importiert.

  **Ruff kann diese Klasse nicht sehen:** bei `target-version = "py310"`
  schlägt UP017 den Kurznamen gar nicht erst vor, verbietet ihn aber auch
  nicht. Und die CI fährt nur pytest und ruff — ein Entwicklungsskript, das
  niemand importiert, bricht dort nie. Der Fehler wäre erst dem aufgefallen,
  der neu aufzeichnen will, und der stünde dann vor einem Werkzeug, das nicht
  startet.

- **Die README nannte einen SDK-Bereich, den `pyproject.toml` nicht
  deklariert.** Der Abschnitt sprach von `mcp>=1.28.1`, deklariert ist
  `mcp>=2.0.0,<3` — eine Major-Version daneben, und genau die, die die zweite
  Protokoll-Aera mitbringt.

### Added

- **`test_der_recorder_laesst_sich_importieren`** macht daraus einen roten
  Test, auf jeder Version der Matrix. Der Test importiert das Skript und ruft
  `main()` nicht auf — es geht um die Ladbarkeit, nicht um einen Lauf gegen die
  Quelle.
- **Eine aufgezeichnete Antwort je Abfrageform**, in `tests/fixtures/`, mit
  Herkunft, Aufnahmedatum, Auswahlregel und SHA-256 je Datei in
  `tests/fixtures/PROVENANCE.md`. Neu aufzeichnen mit
  `PYTHONPATH=src python scripts/record_fixtures.py`, geladen über
  `tests/fixture_data.py`.

  **Je Abfrageform, nicht je Endpunkt.** Dieser Server spricht mit *einem*
  Endpunkt, aber in acht Abfrageformen, und die Form der Antwort hängt an der
  Abfrage: `cube_dimensions` liefert `path`/`kind`/`has_codelist`,
  `cube_observations` liefert `obs`/`p`/`o` — die beiden teilen keine einzige
  Variable. Die Portfolio-Regel «eine Antwort je externem Endpunkt» wäre hier
  mit einer Datei erfüllt und trüge nichts.

  Aufgezeichnet ist die **rohe SPARQL-JSON-Antwort**, nicht das geparste
  Ergebnis: `_parse_bindings` gehört zu dem, was geprüft werden soll. Eine
  Fixture aus fertigen Zeilen überspränge genau den Parser, den sie belegt.

  **Alle acht Aufzeichnungen beschreiben denselben Würfel**, und die beiden
  Gemeinde-Abfragen dieselbe Gemeinde über Name und BFS-Nummer. Zwei erfundene
  Fixtures hätten hier leicht zwei verschiedene Orte gezeigt, ohne dass es
  jemandem auffiele; `test_die_beiden_gemeindeabfragen_beschreiben_denselben_ort`
  hält es fest.
- **`test_der_wahrheitswert_kommt_als_string`** hält eine Falle fest, die erst
  die echte Antwort zeigt: SPARQL liefert `BOUND(?in)` als Literal `"true"` /
  `"false"`, nicht als JSON-Boolean — und `"false"` ist wahr. `cube.py` wandelt
  seit jeher richtig um; der **Recorder** tat es beim ersten Lauf nicht und
  zeichnete eine leere Codeliste auf. Gefangen hat es
  `test_jede_aufzeichnung_traegt_zeilen`: eine leere Fixture sieht aus wie eine
  gültige und prüft nichts.

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
