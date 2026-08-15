# Mitwirken

[🇬🇧 English Version](CONTRIBUTING.md)

Danke für dein Interesse an `lindas-mcp`. Dies ist ein Read-only-MCP-Server über
den öffentlichen LINDAS-SPARQL-Endpunkt; Beiträge sollen das so belassen.

## Grundregeln

- **Read-only.** Jedes Tool bleibt mit `readOnlyHint: true` und
  `destructiveHint: false` annotiert. Keine Schreib-, Sende- oder
  Dateisystem-Fähigkeit. Abfragen gehen nur an den Lese-Endpunkt `/query`; der
  Update-Endpunkt des Stores wird nie kontaktiert.
- **Nur ein Egress-Host.** Anfragen gehen ausschliesslich an den fixen Endpunkt
  `https://lindas.admin.ch/query`, erzwungen durch die `ALLOWED_HOSTS`-Allow-List
  in `src/lindas_mcp/lindas/client.py` (siehe [`docs/network-egress.md`](docs/network-egress.md));
  kein Tool akzeptiert eine nutzergesteuerte URL.
- **Jede Query verankern.** LINDAS läuft bei unverankerten Scans ins Timeout.
  Jedes SPARQL-Template ist auf eine bekannte Klasse verankert (`?x a cube:Cube`);
  nie ein blankes `SELECT * WHERE { ?s ?p ?o }` ergänzen. Der `run_sparql`-Escape
  bleibt gedeckelt (500 Zeilen, 30 s) und als «Advanced» markiert.
- **Keine Secrets.** Der Lese-Endpunkt ist unauthentifiziert; keine
  Credential-Verarbeitung hinzufügen.

## Schichtung

Das `lindas/`-Paket geschichtet halten, damit es unverändert in andere
LINDAS-Server gehoben werden kann:

- `client.py` — rohes SPARQL über HTTP; kennt keine Cubes.
- `queries.py` — verankerte SPARQL-Templates.
- `cube.py` — der cube.link-Vokabular-Guardrail, Zwei-Phasen-Zugriff und
  Code→Label-Auflösung.

Die Tools in `server.py` sprechen nur mit `cube.py`; rohes SPARQL erreicht den
Agenten nie ausser über `run_sparql`.

Die 7 Tool-Definitionen bleiben bewusst zusammen in `server.py`: Jeder Tool-Body
ist ein dünner Wrapper (validieren → `cube.py` aufrufen → Response-Modell formen),
die eigentliche Logik liegt im geschichteten `lindas/`-Paket. Ein `tools/`-Split
würde Indirektion ergänzen, ohne Logik zu verschieben — die Einzeldatei ist also
Absicht, nicht Zufall.

## Entwicklung

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

PYTHONPATH=src pytest tests/ -m "not live"   # offline, respx-gemockt
PYTHONPATH=src pytest tests/ -m live         # gegen den echten Endpunkt
ruff check src tests
```

Die Live-Suite verdient ihren Platz: Die `observationSet`-Indirektion (die
Observations eines Cubes hängen an `cube:observationSet`, nie direkt am Cube)
ist eine Strukturannahme, die ein Mock nicht prüfen kann.

## Pull Requests

- Tests für nutzersichtbare Änderungen ergänzen; `ruff check` und die
  Offline-Suite grün halten.
- Wenn du ein Tool hinzufügst, umbenennst oder seine Argument-Oberfläche änderst,
  `tool-definitions.lock.json` neu generieren (sonst schlägt der SEC-022-CI-Check
  fehl) und in `CHANGELOG.md` vermerken.
- Einen `CHANGELOG.md`-Eintrag unter `[Unreleased]` hinzufügen.
- Bei Doku-Änderungen sowohl `README.md` als auch `README.de.md` aktualisieren.
- Für Release/Publishing siehe [`PUBLISHING.md`](PUBLISHING.md).

## Sicherheitsprobleme melden

Siehe [`SECURITY.md`](SECURITY.md) — bitte privat melden, keine öffentlichen Issues.

## Die Live-Suite: wann sie läuft, und wer ein rotes Ergebnis sieht

**Kadenz:** jeden Montag um 05:17 UTC, dazu jederzeit von Hand über *Actions → Live API tests → Run
workflow*. Siehe [`.github/workflows/live.yml`](.github/workflows/live.yml).

**Wer es sieht:** Ein roter Lauf öffnet ein Issue mit dem Label `upstream` und dem stabilen Titel «Live-Tests gegen lindas.admin.ch rot (<Datum>)». Ein zweiter roter Lauf erkennt das offene Issue am Titelanfang und hängt sich an denselben Thread, statt ein zweites aufzumachen. Wird die Suite wieder grün, schliesst sich das Issue selbst.

**Drei Antworten, nicht zwei.** `scripts/classify_live_run.py` liest das JUnit-XML statt des
Exit-Codes und unterscheidet: `clear` (gelaufen, grün), `finding` (gelaufen,
etwas gefallen) und `unknown` (nicht gelaufen — Installation gescheitert, null
Tests eingesammelt, alle übersprungen). Ein `unknown` schliesst nie ein Issue:
Zuzumachen hiesse zu behaupten, der Vergleich sei gelaufen.

**Ein roter Live-Lauf heisst nicht zwingend «unser Fehler».** Er heisst: Der
Vertrag mit der Quelle hat sich geändert, oder die Quelle ist gerade aus. Beides
gehört gesehen, nur das Erste gehört gefixt. Bitte den Lauf lesen, bevor der Job
deaktiviert wird — so stirbt dieser Check, und er ist der einzige im Repo, der
einer falschen Grundannahme über lindas.admin.ch widersprechen kann. Jeder andere Test
prüft gegen eine Fixture, und die Fixture ist aus derselben Annahme geschrieben
wie der Code.
