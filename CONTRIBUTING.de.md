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
