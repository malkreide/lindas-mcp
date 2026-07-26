# Use Cases & Examples — lindas-mcp

Realitätsnahe Anfragen nach Zielgruppe. LINDAS ist der SPARQL-Wissensgraph des Bundes (betrieben vom Schweizerischen Bundesarchiv) mit rund 2000 statistischen Data Cubes (cube.link). **API-Key nötig: Nein** — der Lesezugriff auf den LINDAS-Endpunkt ist ohne Authentifizierung möglich.

> Merksatz des Servers: «Struktur vor Daten.» Zuerst die Dimensionen und Measures eines Cubes lesen (`get_cube_structure`), dann erst die Observations abfragen — so kommen Codes als Labels zurück, nicht als rohe Nummern.

## 🏫 Bildung & Schule

**«Welche Waldbrand-Gefahrenstufe gilt aktuell, wer publiziert das, und unter welcher Lizenz?»**
- **API-Key nötig:** Nein
- → `search_cubes(query="waldbrand", language="de")`
- → `get_cube_structure(cube_uri="<URI aus der Suche>")`
- → `query_cube_observations(cube_uri="<URI>", resolve_labels=True)`
- Warum nützlich: Aus einem Stichwort werden eine benannte Behörde (BAFU), eine konkrete Lizenz (oft eine Fedlex-URI) und Datenpunkte mit lesbaren Labels («grosse Gefahr» statt `4`) — im Unterricht direkt verwertbar.

**«Welche Bundesämter publizieren überhaupt statistische Cubes, und zu welchem Thema?»**
- **API-Key nötig:** Nein
- → `list_publishers()`
- → `search_cubes(query="<Thema>", creator_uri="<URI eines Amts>")`
- Warum nützlich: Zeigt die publizierenden Stellen mit Cube-Anzahl und erlaubt, eine Suche gezielt auf eine Behörde einzuschränken — ideal für ein Rechercheprojekt über amtliche Statistik.

## 👨‍👩‍👧 Eltern & Schulgemeinde

**«Gibt es amtliche Zahlen zu unserer Gemeinde, und wie heisst sie in den Daten?»**
- **API-Key nötig:** Nein
- → `resolve_municipality(name_or_bfs="Uster")`
- → `search_cubes(query="Gemeinde", language="de")`
- Warum nützlich: `resolve_municipality` liefert die BFS-Gemeindenummer und die LINDAS-URI (`ld.admin.ch/municipality/<BFS>`) — der Schlüssel, über den Gemeindedaten in Cubes und in anderen Portfolio-Servern referenziert werden.

**«Ich habe eine BFS-Nummer aus einem Formular — welche Gemeinde ist das?»**
- **API-Key nötig:** Nein
- → `resolve_municipality(name_or_bfs="198")`
- Warum nützlich: Übersetzt eine nackte Verwaltungsnummer zurück in einen Ortsnamen, ohne manuelle Tabellen.

## 🗳️ Bevölkerung & öffentliches Interesse

**«Welche Lizenz gilt für diese Daten, und darf ich sie weiterverwenden?»**
- **API-Key nötig:** Nein
- → `get_cube_structure(cube_uri="<URI>")`
- Warum nützlich: Das `licence`-Feld ist pro Cube deklariert und oft eine Fedlex-Rechtsgrundlagen-URI. So gelangt man von einem Datenpunkt direkt zur rechtlichen Grundlage — auflösbar mit [`fedlex-mcp`](https://github.com/malkreide/fedlex-mcp).

**«Existiert schon ein offizieller Datensatz zu einem Thema, bevor jemand selbst zählt?»**
- **API-Key nötig:** Nein
- → `search_cubes(query="<Thema>", latest_only=True)`
- Warum nützlich: `latest_only` dedupliziert Versionen und liefert nur die neuste publizierte — kein Rauschen aus alten Cube-Versionen.

## 🤖 KI-Interessierte & Entwickler:innen

**«Ist LINDAS gerade erreichbar, und wie viele Cubes stehen zur Verfügung?»**
- **API-Key nötig:** Nein
- → `api_status()`
- Warum nützlich: Liefert immer einen auswertbaren Status (erreichbar + Cube-Anzahl vs. down) statt eines stillen Leerergebnisses — ein Agent kann «keine Treffer» von «Quelle nicht erreichbar» unterscheiden.

**«Ich brauche einen Cross-Cube-Join oder eine Aggregation, die die Tools nicht abdecken.»**
- **API-Key nötig:** Nein
- → `run_sparql(query="PREFIX cube: <https://cube.link/> SELECT ... WHERE { ?c a cube:Cube ... }")`
- Warum nützlich: Der Escape-Hatch für Fortgeschrittene. **Immer** auf eine bekannte Klasse verankern (`?x a cube:Cube`) — ein blankes `SELECT * WHERE { ?s ?p ?o }` läuft ins Timeout. Gedeckelt auf 500 Zeilen und 30 s.

## 🔧 Technische Referenz: Tool-Auswahl nach Anwendungsfall

| Ich möchte… | Tool(s) | Auth nötig? |
|---|---|---|
| Cubes per Thema finden (Einstieg, versions-dedupliziert) | `search_cubes` | Nein |
| Dimensionen, Measures und Lizenz eines Cubes lesen (Phase 1) | `get_cube_structure` | Nein |
| Datenpunkte abrufen, Codes automatisch als Labels (Phase 2) | `query_cube_observations` | Nein |
| Publizierende Bundesämter mit Cube-Anzahl auflisten | `list_publishers` | Nein |
| Gemeinde ↔ URI ↔ BFS-Nummer auflösen (Portfolio-Join-Key) | `resolve_municipality` | Nein |
| Einen eigenen SPARQL-Join / eine Aggregation fahren (Advanced) | `run_sparql` | Nein |
| Erreichbarkeit der Quelle prüfen (mit Graceful Degradation) | `api_status` | Nein |

## Join-Keys zum übrigen Portfolio

| Schlüssel | Wo | Verbindet zu |
|---|---|---|
| BFS-Gemeindenummer | `resolve_municipality` → `bfs_number` | swiss-statistics-mcp, zurich-opendata-mcp |
| Fedlex-URI | Cube-Feld `licence` | [fedlex-mcp](https://github.com/malkreide/fedlex-mcp) |
| Datensatz-Existenz | I14Y als Katalog | [i14y-mcp](https://github.com/malkreide/i14y-mcp) |
