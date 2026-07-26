# Sicherheitsrichtlinie & Posture

[🇬🇧 English Version](SECURITY.md)

`lindas-mcp` ist ein **Read-only-**, **No-Auth-**, **Public-Open-Data-**MCP-Server.
Dieses Dokument fasst die Sicherheits-Posture zusammen und beschreibt, wie
Schwachstellen gemeldet werden.

## Schwachstelle melden

Bitte ein privates Security Advisory im GitHub-Repository eröffnen oder die in
`README.md` genannte Maintainerin kontaktieren. Für ausnutzbare Schwachstellen
keine öffentlichen Issues erstellen.

## Posture-Zusammenfassung

Alle 7 Tools stellen ausschliesslich Lese-Abfragen (`SELECT`/`ASK`) an den
öffentlichen LINDAS-Endpunkt (`lindas.admin.ch/query`); es gibt keine Schreib-,
Sende- oder Dateisystem-Fähigkeiten, und es werden keine Personendaten
verarbeitet — der Server stellt ausschliesslich Cube-Metadaten und Observations
bereit.

| Bereich | Kontrolle |
|---|---|
| Egress | Code-Layer-Allow-List (`frozenset({"lindas.admin.ch"})`, nicht env-konfigurierbar), geprüft bevor der Client gebaut wird; `follow_redirects=False` verweigert jeden Off-Host-Redirect; kein Tool akzeptiert eine nutzergesteuerte URL, daher keine SSRF-Angriffsfläche am Client. Siehe [`docs/network-egress.md`](docs/network-egress.md) |
| TLS | httpx-Zertifikatsprüfung standardmässig aktiv und im Code nie deaktiviert |
| Auth / Secrets | Unauthentifizierter öffentlicher Lese-Endpunkt — es werden keine API-Keys, Tokens oder Secrets gespeichert oder weitergereicht. Es wird nur der Lese-Endpunkt `/query` kontaktiert; der Update-Endpunkt des Stores wird nie genutzt |
| Input | Pydantic-v2-Validierung an allen Tool-Grenzen; Zeilen- und Zeit-Caps werden geklammert; jedes eingebaute Query-Template ist auf eine bekannte Klasse verankert (`?x a cube:Cube`), um unbegrenzte Store-Scans zu verhindern |
| `run_sparql` | Escape-Hatch für Fortgeschrittene, gedeckelt bei 500 Zeilen und 30 s. Er reicht eine rohe SPARQL-Abfrage an den Lese-Endpunkt `/query` weiter; eine `SPARQL`-`SERVICE`-Klausel (Federation) wird vom Upstream-Store ausgeführt, nicht von diesem Server — der Server selbst verbindet sich nur mit `lindas.admin.ch`. `run_sparql` ist das einzige Tool mit breiter Eingabefläche und bleibt als «Advanced» markiert |
| Tools | Alle mit `readOnlyHint: true`, `destructiveHint: false` annotiert; keine dynamische oder Remote-Tool-Registrierung |
| Fehler | Eine fehlerhafte Query liefert die eigene `400`-Diagnose des Endpunkts als strukturierten Fehler; transiente Fehler werden mit Backoff wiederholt; `api_status` liefert immer einen auswertbaren Zustand (erreichbar vs. down) |
| Stdout | Reserviert für den JSON-RPC-Stream; der Server gibt kein Fremd-Logging auf stdout aus |
| Binding | `stdio` als Default (keine Netzwerk-Angriffsfläche). SSE / streamable-http bindet an `HOST`, **Default `127.0.0.1` (Loopback)**; `0.0.0.0` ist ein expliziter Opt-in (das Container-Image setzt es bewusst) und warnt auf stderr |

## Akzeptierte Risiken (Kontrollen auf Portfolio-Ebene)

Die folgenden Punkte werden auf der MCP-Gateway-/Host-Ebene behandelt, nicht in
diesem einzelnen Server. Das Restrisiko ist hier gering, weil der Server
read-only und unauthentifiziert ist und nur einen vertrauenswürdigen
Open-Data-Endpunkt erreicht.

- **Session-Krypto-Bindung** — nicht anwendbar: Es gibt keine Nutzeridentität zum
  Binden, da der Server öffentliche Daten ohne Authentifizierung bereitstellt.
- **Tool-Allow-Listing & server-übergreifende Tool-Poisoning-Erkennung** (SEC-014,
  SEC-015) — Aufgabe des Gateways/Hosts, als Kontrolle auf Portfolio-Ebene
  akzeptiert. Dieser Server hat kein Auth-Modell und keine Rollen, es gibt also
  serverseitig nichts zu gaten; seine Tool-Definitionen sind versioniert, in-repo
  verfasst und per PR reviewt, ohne dynamische oder Remote-Tool-Registrierung. Als
  Rug-Pull-Schutz wird ein Hash-Snapshot jedes Tool-Namens und seiner
  Argument-Oberfläche (Argument-Namen + required-Set) in
  [`tool-definitions.lock.json`](tool-definitions.lock.json) committet und in der
  CI geprüft (SEC-022) — jede stille Änderung des Tool-Sets oder eines
  Tool-Vertrags lässt den Build fehlschlagen. Bei Aggregation hinter einem
  gemeinsamen Gateway dessen Tool-Allow-Listing und Tool-Poisoning-Erkennung
  aktivieren.
- **Tool-Namespacing** (SEC-022) — die Tool-Namen bleiben bewusst ohne Präfix
  (`search_cubes`, nicht `lindas__search_cubes`), zwecks Konsistenz über das
  Swiss-Public-Data-MCP-Portfolio. Server-übergreifendes Tool-Shadowing ist ein
  Multi-Server-Thema und wird am aggregierenden Gateway behandelt; innerhalb
  dieses einzelnen, in-repo, per PR reviewten Servers verhindert der
  `tool-definitions.lock.json`-Hash bereits stille Änderungen der
  Tool-Oberfläche. Als Kontrolle auf Portfolio-Ebene akzeptiert; führt das
  Portfolio Präfixe ein, werden sie einheitlich über alle Server angewandt.
- **Netzwerk-Binding für gehostete Deployments** — der SSE-/streamable-http-
  Transport bindet an `HOST`, standardmässig `127.0.0.1` (Loopback). Ein Binding
  an `0.0.0.0` ist ein expliziter Opt-in (das Container-Image setzt es bewusst)
  und warnt auf stderr. Jedes `0.0.0.0`-Deployment mit einem Reverse-Proxy /
  Gateway betreiben, das TLS und Zugriffskontrolle erzwingt; der Default-Transport
  (`stdio`) hat gar keine Netzwerk-Angriffsfläche. Über HTTP exponiert CORS
  ausschliesslich den `Mcp-Session-Id`-Response-Header (den Browser-MCP-Clients
  benötigen).

## Re-Evaluations-Trigger

Diese Akzeptanzen sind neu zu bewerten, sobald der Server je:

- **Schreib**-Fähigkeit erhält oder **PII** verarbeitet, oder
- ein **Authentifizierungs**-Modell erhält (dann gebundene, TTL-behaftete,
  serverseitig invalidierbare Session-IDs implementieren und vor dem Merge
  re-auditieren), oder
- Tools **dynamisch** / aus Remote-Quellen registriert, oder
- hinter einem gemeinsamen MCP-Gateway aggregiert wird (dann Tool-Allow-Listing
  und Tool-Poisoning-Erkennung des Gateways aktivieren).
