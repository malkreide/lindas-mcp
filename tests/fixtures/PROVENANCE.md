# Herkunft der Fixtures

**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**

Aufgezeichnet am **2026-08-15** vom Endpunkt dieses Servers:
`https://lindas.admin.ch/query`.

Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht
mehr zu unterscheiden — die Datei sieht gleich aus.

**Ein Endpunkt, sieben Abfrageformen.** Die Form der Antwort haengt hier
an der Abfrage und nicht am Endpunkt: `cube_dimensions` liefert andere
Variablen als `cube_observations`, und ein Stub, der beide gleich raet,
faellt nie auf. Aufgezeichnet ist deshalb eine Antwort je Abfrageform.

**Aufgezeichnet ist die rohe SPARQL-JSON-Antwort**, nicht das geparste
Ergebnis. `_parse_bindings` gehoert zu dem, was geprueft werden soll; eine
Fixture aus fertigen Zeilen wuerde genau den Parser ueberspringen, den sie
belegen soll.

**Alle Aufzeichnungen beschreiben denselben Wuerfel.** Der erste Treffer
der Suche bestimmt, welcher — Metadaten, Dimensionen, Beobachtungen und
Codeliste gehoeren damit zusammen und nicht zu sieben verschiedenen
Gegenstaenden. Dasselbe gilt fuer die beiden Gemeinde-Abfragen: sie
treffen dieselbe Gemeinde ueber Name und BFS-Nummer.

Fehlerpfade — Timeouts, 5xx, eine kaputte Abfrage mit HTTP 400 — bleiben
handgeschrieben. Die lassen sich nicht auf Zuruf aufzeichnen.

## `search_cubes.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+cube%3A+%3Chttps%3A%2F%2Fcube.link%2F%3E%0APREFIX+sh%3A+%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fshacl%23%3E%0APREFIX+sch`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; Suche nach 'bevölkerung', limit 5. Der erste Treffer (https://environment.ld.admin.ch/foen/ubd003701/6) ist der Wuerfel aller folgenden Aufzeichnungen — sie beschreiben damit **denselben** Gegenstand und nicht sieben zufaellige
- **Groesse:** 7095 B (5 Ergebniszeilen)
- **SHA-256:** `55b12a455c4424276d4bfdd61226f5c3c6055a83697078c2b99953029988b078`

## `cube_metadata.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+cube%3A+%3Chttps%3A%2F%2Fcube.link%2F%3E%0APREFIX+sh%3A+%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fshacl%23%3E%0APREFIX+sch`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; Metadaten des Wuerfels
- **Groesse:** 1252 B (1 Ergebniszeilen)
- **SHA-256:** `768eb7386aa65dc708a714287681b9c37500c72906a0a715a4fb1521a712cdd8`

## `cube_dimensions.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+cube%3A+%3Chttps%3A%2F%2Fcube.link%2F%3E%0APREFIX+sh%3A+%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fshacl%23%3E%0APREFIX+sch`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; Dimensionen des Wuerfels — andere Variablen als jede andere Form
- **Groesse:** 3726 B (7 Ergebniszeilen)
- **SHA-256:** `9213f15a73dea18db514fd5e06c5836f682ca983ca901d1a66aeaa31e91cb7fe`

## `cube_observations.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+cube%3A+%3Chttps%3A%2F%2Fcube.link%2F%3E%0APREFIX+sh%3A+%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fshacl%23%3E%0APREFIX+sch`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; 5 Beobachtungen als Tripel (`obs`/`p`/`o`); der Server dreht sie erst danach in Zeilen
- **Groesse:** 2308 B (5 Ergebniszeilen)
- **SHA-256:** `10244d2dec1755ecf0af3d43847f2c0de32d30e6484c995c1625a340bc6d5ebd`

## `list_creators.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+cube%3A+%3Chttps%3A%2F%2Fcube.link%2F%3E%0APREFIX+sh%3A+%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fshacl%23%3E%0APREFIX+sch`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; vollstaendig; alle Herausgeber mit Wuerfelzahl
- **Groesse:** 4383 B (13 Ergebniszeilen)
- **SHA-256:** `72ecdb56415af7ac9a476ffb70b0490ef66f8ab24fa236fc87f4496d89cda753`

## `municipality_by_name.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+cube%3A+%3Chttps%3A%2F%2Fcube.link%2F%3E%0APREFIX+sh%3A+%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fshacl%23%3E%0APREFIX+sch`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; Gemeinde 'Winterthur' ueber den Namen
- **Groesse:** 506 B (1 Ergebniszeilen)
- **SHA-256:** `1160dd3eb41ae3f155f6e0b1f9e3fa788fafb68151bbc2e85ec1608da6e293ea`

## `municipality_by_bfs.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+cube%3A+%3Chttps%3A%2F%2Fcube.link%2F%3E%0APREFIX+sh%3A+%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fshacl%23%3E%0APREFIX+sch`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; BFS-Nummer 230 — **dieselbe** Gemeinde wie oben, ueber den zweiten Weg. Damit belegt das Paar, dass beide Wege denselben Datensatz treffen
- **Groesse:** 506 B (1 Ergebniszeilen)
- **SHA-256:** `1160dd3eb41ae3f155f6e0b1f9e3fa788fafb68151bbc2e85ec1608da6e293ea`

## `dimension_codelist.json`

- **Quelle:** `https://lindas.admin.ch/query?query=%0APREFIX+cube%3A+%3Chttps%3A%2F%2Fcube.link%2F%3E%0APREFIX+sh%3A+%3Chttp%3A%2F%2Fwww.w3.org%2Fns%2Fshacl%23%3E%0APREFIX+sch`
- **Aufgezeichnet:** 2026-08-15
- **Auswahl:** vollstaendig; die Codeliste der ersten Dimension des Wuerfels, die eine fuehrt (https://environment.ld.admin.ch/foen/ubd003701/verkehrsart). Ohne sie bleibt die Code-zu-Label-Aufloesung ungeprueft
- **Groesse:** 1650 B (4 Ergebniszeilen)
- **SHA-256:** `6e6d88c8185c170ec68a44c11992152bebb82225af4c65c14d10dad3302a0d68`
