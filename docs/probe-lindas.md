# Live-Probe: LINDAS (Linked Data Service der Bundesverwaltung)

**Datum:** 21. Juli 2026
**Prüfer:** `mcp-data-source-probe` (Schritt 1)
**Quelle:** https://lindas.admin.ch — Betrieb: Schweizerisches Bundesarchiv (BAR)

---

## 1.1 Dokumentation

| Aspekt | Befund |
|---|---|
| SPARQL-Endpunkt | `https://lindas.admin.ch/query` (HTTP 200, live verifiziert) |
| Alias-Endpunkt | `https://ld.admin.ch/query` (identisch, ebenfalls 200) |
| Protokoll | SPARQL 1.1 Query über HTTP, GET und POST |
| Server-Header | `nginx` (dahinter Fuseki/Stardog-Klasse, nicht offengelegt) |
| Auth | **keine** für Lesezugriffe — No-Auth-First erfüllt |
| Federation | `SERVICE`-Klausel funktioniert (Self-Federation getestet, HTTP 200) |
| Vokabular-Doku | https://cube.link (Cube-Schema), https://schema.ld.admin.ch (Geo/Admin) |
| Visualisierungs-Frontend | https://visualize.admin.ch läuft auf denselben Cubes |

**Kein REST-API, kein Dump im klassischen Sinn.** Der Zugang ist ausschliesslich
SPARQL. Das ist Chance und Hürde zugleich (siehe Architektur-Entscheid).

---

## 1.2/1.3 Befund-Tabelle

| Test | HTTP | Zeit | Befund |
|---|---|---|---|
| Endpunkt-Ping (`SELECT ... LIMIT 1`) | 200 | 0.19 s | ✅ erreichbar, ohne Auth |
| `COUNT(DISTINCT cube)` | 200 | 1.76 s | ✅ **1985 Cubes** |
| Cubes nach Publisher (GROUP BY) | 200 | 0.19 s | ✅ BLW, Bundeskanzlei, WSL, ElCom, BAFU |
| Cube-Suche (`FILTER CONTAINS`) | 200 | 0.19 s | ✅ funktioniert, aber teuer bei Volltext |
| Cube-Struktur (SHACL `sh:property`) | 200 | 0.30 s | ✅ Dimensionen + Measures auslesbar |
| Observations abrufen | 200 | 0.30 s | ✅ echte Datenpunkte, Codes statt Labels |
| Gemeinde-URI-Auflösung | 200 | 0.19 s | ✅ `ld.admin.ch/municipality/<BFS>` |
| Malformed SPARQL | 400 | 2.28 s | ✅ klare `MALFORMED QUERY`-Meldung mit Position |
| `COUNT(*)` über ganzen Store | **000** | 70 s | ❌ **Timeout** — Full-Store-Scan nicht erlaubt |
| `DISTINCT ?g` über alle Graphs | **000** | 90 s | ❌ **Timeout** — blinder Graph-Scan nicht erlaubt |
| Content-Negotiation JSON/CSV/XML | 200 | — | ✅ alle drei Formate |
| POST für lange Queries | 200 | 0.29 s | ✅ `Content-Type: application/sparql-query` |

---

## 1.4 Reality-Check

| Aussage aus der Portfolio-Analyse | Verifiziert? |
|---|---|
| «Hydrodaten hängen dran» | teilweise — BAFU-Umweltcubes vorhanden, Hydro-Cubes über `environment.ld.admin.ch` zu bestätigen |
| «Geo-Linked-Data» | ✅ Gemeinde-URIs mit BFS-Nummer live bestätigt |
| «Basis von visualize.admin.ch» | ✅ dieselben Cubes, dasselbe `cube.link`-Vokabular |
| «~2000 Cubes» | ✅ exakt 1985 |

---

## Fundstücke

**1 — Blinde Scans laufen ins Timeout, gezielte Queries sind schnell.**
`COUNT(*)` über den ganzen Store und `DISTINCT ?g` über alle Named Graphs
liefen beide 70–90 s in den Timeout (HTTP 000). Dieselbe Information, aber am
`cube.link`-Vokabular verankert (`COUNT(DISTINCT ?cube WHERE ?cube a cube:Cube)`),
antwortet in 1,8 s.

> *Eselsbrücke: «LINDAS belohnt, wer weiss, wonach er fragt — und bestraft,
> wer alles will.»* Der MCP-Server muss den Agenten zwingen, immer am
> Vokabular zu verankern. Freie Scans sind der häufigste Fehler.

**2 — Dimensionswerte kommen als Codes, nicht als Labels.**
Eine Observation liefert `region: 1805`, `level: 4`, `canton: 11` — nicht
«Warnregion Alpennordhang», «erhebliche Gefahr», «Freiburg». Die Auflösung
Code → Label ist ein zweiter Schritt über die SHACL-Shape des Cubes. Ein
Server, der rohe Codes zurückgibt, ist für den Agenten wertlos.

> *Metapher: «LINDAS spricht in Postleitzahlen, nicht in Ortsnamen.»*

**3 — Die Gemeinde-URI trägt die BFS-Nummer im Klartext.**
`https://ld.admin.ch/municipality/261` = Zürich, und 261 ist die amtliche
BFS-Gemeindenummer. Das ist der portfolioweite Join-Key, wörtlich in der URI.
Kein Namensabgleich nötig, keine Wikidata-Disambiguierung.

**4 — Das Vokabular ist vollständig fünfsprachig.**
Cube-Namen und Dimensions-Labels liegen in de/fr/it/rm/en plus einem
sprachlosen Default vor. Dieselbe `pick_lang()`-Logik wie in `i14y-mcp` und
`fedlex-mcp` ist wiederverwendbar.

**5 — Cubes sind versioniert, und die Version steckt in der URI.**
`.../nfi_C-501/cube/2023-1`, `2023-2`, `2024-1` — derselbe logische Cube
existiert in mehreren Versionen als eigenständige URIs. Ein `search_cubes`
ohne Deduplizierung liefert denselben Cube mehrfach. Die neueste Version muss
aktiv ermittelt werden (`schema:version` oder URI-Suffix-Sortierung).

**6 — Der Observation-Zugriff geht über `observationSet`, nicht direkt.**
Muster: `?cube cube:observationSet ?set . ?set cube:observation ?obs`. Der
naive Direktzugriff `?cube cube:observation ?obs` liefert null Zeilen. Real
beobachtet in dieser Probe — die erste Query-Variante war leer, bis der
`observationSet`-Zwischenschritt ergänzt wurde.

---

## 1.5 Dump-Verfügbarkeit

Kein klassischer Dump. LINDAS ist ein Live-Triplestore. Einzelne Cubes lassen
sich per SPARQL CONSTRUCT oder über die Distribution-Links in I14Y als
CSV/RDF exportieren, aber es gibt keinen Gesamt-Download. Für einen MCP-Server
ist das unerheblich — der Zugriff ist ohnehin abfragebasiert.

---

## Lizenz

LINDAS-Daten stehen grundsätzlich unter offenen Lizenzen (meist
«Opendata BY ASK» / «BY»), aber die Lizenz wird **pro Cube** über
`dcterms:license` bzw. `schema:license` deklariert und variiert je Publisher.
Konsequenz identisch zu `i14y-mcp`: Die Lizenz gehört in jede Server-Antwort,
die Cube-Daten liefert. «Im offenen Triplestore» ist nicht «frei verwendbar».

---

## Cube-Vokabular (Referenz für die Implementation)

Minimaldokumentation des `cube.link`-Modells, wie in dieser Probe verifiziert:

```
?cube  a  cube:Cube ;
       schema:name         "..."@de ;          # fünfsprachig
       schema:publisher    ?publisher ;
       cube:observationConstraint ?shape ;      # die SHACL-Struktur
       cube:observationSet ?set .

?shape sh:property ?prop .
?prop  sh:path      ?dimensionPath ;            # die Dimension/Measure
       schema:name  "..."@de ;
       a            cube:KeyDimension            # ODER
                    cube:MeasureDimension .

?set   cube:observation ?obs .
?obs   ?dimensionPath ?value .                   # ?value oft ein Code-URI
```

**Zwei-Phasen-Zugriff, den der Server kapseln muss:**
1. Struktur lesen (`observationConstraint` → Dimensionen, Measures, Codelisten)
2. Daten lesen (`observationSet` → `observation` → Werte), Codes gegen die
   Struktur aus Phase 1 auflösen

---

## Architektur-Entscheid

**ARCH A — Live-SPARQL-only, mit striktem Vokabular-Guardrail.**

Begründung:
- Endpunkt stabil, ohne Auth, mit sauberem 400 bei Syntaxfehlern.
- Kein Dump nötig; abfragebasierter Zugriff ist der native Modus.
- Aber: Der Store ist gross genug, dass blinde Queries ins Timeout laufen.
  Der Server darf dem Agenten **kein rohes SPARQL ohne Leitplanken** geben.

Konsequenzen für die Tool-Gestaltung:
- **Vokabular-Verankerung erzwingen.** Jede Discovery-Query filtert auf
  `?x a cube:Cube` oder eine bekannte Klasse. Nie `SELECT * WHERE {?s ?p ?o}`.
- **Zwei-Phasen-Zugriff kapseln.** `get_cube_structure` vor
  `query_cube_observations` — der Agent soll nie rohe Codes ohne Labels sehen.
- **Code→Label-Auflösung eingebaut**, nicht dem Agenten überlassen.
- **`run_sparql` nur als Escape-Hatch** mit hartem Timeout (< 30 s) und
  Ergebnis-Limit, klar als Fortgeschrittenen-Tool markiert.
- **Versions-Deduplizierung** in `search_cubes`.
- **`pick_lang()` aus i14y-mcp/fedlex-mcp wiederverwenden.**
- **Timeout clientseitig auf ~45 s** setzen; der Server läuft sonst selbst in
  den 60–90-s-Serverabbruch und liefert HTTP 000 an den Agenten weiter.

---

## Empfehlung zur Umsetzungsreihenfolge

Nicht sofort als eigenständiger `lindas-mcp`. Stattdessen:

1. **SPARQL-Client zuerst im konkreten Fall** — als Teil der
   `swiss-environment-mcp`-Erweiterung (BAFU-Hydrodaten liegen in LINDAS).
   Dort das Cube-Vokabular an einem nützlichen Beispiel lernen.
2. **Client extrahieren**, sobald ein zweiter Server ihn braucht
   (`wsl-envidat-mcp`, künftiger Geo-Server).
3. **Dann `lindas-mcp`** als Discovery-Server über den 1985 Cubes — mit
   erprobtem Vokabular-Wissen, nicht auf der grünen Wiese.

Begründung: Ein `lindas-mcp` ohne vorherige Cube-Erfahrung wird entweder zu
dünn (nur `run_sparql`, verlagert die Komplexität auf den Agenten) oder zu
breit (ein Tool pro Cube-Typ, sprengt das Budget). Erst am Fall lernen,
dann verallgemeinern — dein eigenes Prinzip.

---

## Vorschlag Tool-Design (für Phase 2, nach «go»)

Budget: 6 Tools, bewusst schlank, weil SPARQL mächtig ist.

| Tool | Zweck |
|---|---|
| `search_cubes(query, publisher?, theme?, latest_only=True)` | Cubes im Katalog finden, versions-dedupliziert |
| `get_cube_structure(cube_uri)` | Dimensionen, Measures, Codelisten auslesen — Phase 1 |
| `query_cube_observations(cube_uri, filters, limit)` | Datenpunkte, Codes automatisch zu Labels aufgelöst — Phase 2 |
| `resolve_municipality(name_or_bfs_number)` | Name ↔ URI ↔ BFS-Nummer, der Join-Key |
| `list_publishers()` | publizierende Ämter, mit Cube-Anzahl |
| `run_sparql(query, timeout_s=30)` | Escape-Hatch, hart limitiert, als Advanced markiert |

**Anchor Demo Query:**
«Welche Waldbrand-Gefahrenstufe gilt aktuell in den Warnregionen des Kantons
Zürich, und wer publiziert diese Daten?»
