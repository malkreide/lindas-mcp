# CLAUDE.md

## Teil 1 — Portfolio-Konventionen

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.

Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  `asyncio` selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

**Ein 4xx ist kein Nein.** Am 29.8.2026 antwortete `past-publications` in
`swiss-procurement-mcp` auf jede Publikation mit Losen mit HTTP 400. Daraus war
geschlossen worden, die Quelle verweigere diese Auskunft; der Befund stand
datiert im Fixture-Nachweis, ein Test bestätigte ihn, alles blieb grün. Die
Spec desselben Endpunkts führt einen als *optional* deklarierten Parameter
`lotId` — für Publikationen mit Losen ist er Pflicht. Mit ihm antwortet
dieselbe Publikation mit 200. Ein Projekt trug sieben Vorgängerpublikationen,
die der Server als «Quelle nicht erreichbar» wegwarf.

Drei Handgriffe daraus:

- **Die Parameterliste der Spec durchgehen, bevor ein Statuscode eingeordnet
  wird.** «Optional» heisst dort oft «optional für die Mehrheit».
- **Einer deterministischen Absage keinen Wiederholungsrat geben.** «Nicht
  erreichbar, bitte später erneut» ist bei einem 400 falsch und liest sich für
  das Modell wie eine Störung. Den Status mitführen und den fehlenden
  Parameter benennen — den Status, nicht den Antwortkörper.
- **Beide Antworten aufzeichnen, mit und ohne den Parameter.** Eine
  Aufzeichnung nur des Fehlschlags kann nicht zeigen, dass er vermeidbar war;
  dass nur der 400er aufgezeichnet war, ist der Grund, warum der falsche
  Befund nicht auffiel.

**Und ein 403 ist gar keine Auskunft.** Am 29.8.2026 sollten für 42 Repos die
Dependabot-Labels nachgemessen werden. Alle 13 Abfragen des ersten Stapels
kamen zurück als:

```
Failed to find label: API rate limit already exceeded for user ID 8864492.
```

Der gefährliche Teil steht vorn: Das Werkzeug verpackt eine Sperre als
Fund-Fehlschlag. Wer die Zeile überfliegt oder nur auf ein leeres Ergebnis
prüft, zählt 39 Repos als «Label fehlt» und hat seine eigene Erschöpfung
gemessen. Das Limit hängt am Konto, nicht am Repo — derselbe Vormittag hatte
es mit 42 eröffneten und 42 gemergten PRs verbraucht.

Das ist der Absatz darüber, andersherum gelesen: dort war ein 400 eine echte,
wiederholbare Antwort und galt als Störung; hier ist eine Störung als Antwort
verpackt. Entscheidend ist nie der Statuscode, sondern ob die Quelle überhaupt
geantwortet hat.

- **Positivkontrolle im selben Repo.** Ein «nicht gefunden» wird erst dadurch
  zur Messung, dass eine gleichzeitige Abfrage etwas findet.
- **Die Messung entlang der Sperre teilen.** `raw.githubusercontent.com` ist
  ein CDN und nicht die REST-API. Um 11:19:27 UTC lieferte es für
  `register-mcp` HTTP 200, während die Label-Abfrage desselben Repos in
  derselben Minute die Sperre meldete. Alle 42 `dependabot.yml` kamen so
  durch, während die Label-Hälfte stand.
- **Am Token vorbei geht es nicht.** Beide Umwege enden am Agent-Proxy, und
  jeder mit einer eigenen irreführenden Begründung. `api.github.com` ohne
  Zugangsdaten:

  ```
  GitHub access is not enabled for this session. An org admin must connect
  the Claude GitHub App for this organization.
  ```

  Das ist keine Aussage über die Organisation, sondern das, was ohne Token
  kommt. Wer ihr folgt, sucht einen Admin für ein Problem, das keiner hat.
  Die HTML-Seite `github.com/<owner>/<repo>/labels` fällt ebenfalls, aber
  anders:

  ```
  This GitHub API path is not available: sessions are bound to their
  configured repositories. Use repository-scoped endpoints
  (repos/{owner}/{repo}/...).
  ```

  Der Proxy behandelt also auch `github.com` als API-Pfad; die zweite Meldung
  klingt nach einem Scope-Problem und ist doch nur dieselbe Sackgasse. Den
  Token aus der Umgebung in einen curl-Header zu setzen, blockiert der
  Klassifikator. Ob es überhaupt hülfe, ist offen: die Sperre nennt ein
  Nutzerkonto, und ob der Token zu diesem gehört, wurde nie geprüft.
- **Die Sperre gilt nicht dem Dienst, sondern dem Zugangspfad.** Unmittelbar
  nachdem eine Abfrage der Checks eines PR sauber durchlief, meldete die
  Label-Abfrage weiter die Sperre. Von einem blockierten Werkzeug also nicht
  auf «GitHub ist zu» schliessen — und umgekehrt eine gelungene Abfrage nicht
  als Entwarnung für die gesperrte nehmen.

Wann die Sperre fällt, geben diese Beobachtungen nicht her. Die Meldung nennt
keinen Zeitpunkt, und die `X-RateLimit`-Kopfzeilen sind hinter dem Proxy nicht
zu sehen. Belegt sind drei gesperrte Zeitpunkte — 11:14, 11:16 und 11:19 UTC.
Wer daraus eine Dauer macht, hat sie erfunden.

**Dieselbe Falle bei einer Konfigurationsoption: die Vorgabe lesen, bevor man
einen Schlüssel für wirkungslos hält.** Am 29.8.2026 fielen die
`labels:`-Zeilen aus den `dependabot.yml` des Portfolios, begründet mit
«Dependabot legt Labels nicht an». Eine Messung danach zeigte, dass
`dependencies` in 36 von 42 Repos sehr wohl existiert, 35 davon mit GitHubs
Standardbeschreibung. Das las sich zuerst wie ein Beleg, dass die Aktion
falsch war.

Die Optionsreferenz kehrt es um:

```
Dependabot creates these default labels automatically, as necessary in
your repository.

If you define more than one package manager, an additional label for the
ecosystem or language is added to each pull request.

The labels specified are used instead of the default labels.
```

Ohne `labels:` vergibt Dependabot also `dependencies` — und, sobald mehr als
ein Paketmanager deklariert ist, zusätzlich ein Ökosystem-Label — und legt sie
selbst an; eine eigene Liste **ersetzt** diesen Satz, und «if any of these
labels is not defined in the repository, it is ignored». Die Zeile war nicht
wirkungslos — sie tauschte einen sich selbst pflegenden Vorgabesatz gegen eine
starre Liste.

**Die Bedingung nicht weglassen.** Bei nur einem Paketmanager steht das
Ökosystem-Label gar nicht zu; wer es dort trotzdem erwartet, schreibt genau
den Fehlbefund auf, gegen den dieser Abschnitt geschrieben ist — der Abschnitt
liefe an sich selbst vorbei. Im Portfolio deklariert jede `dependabot.yml`
zwei (`pip` und `github-actions`), die Bedingung ist hier also überall
erfüllt; anderswo nicht unbedingt. Aufgefallen ist die fehlende Bedingung
nicht beim Schreiben, sondern durch einen Codex-Review auf
`swiss-environment-mcp` PR #113 — vierzehn Sekunden vor dem Merge desselben
PR.

Was das kostet, ist an `openlex-mcp` gemessen: zwei Ökosysteme deklariert,
also stünden `dependencies` **und** ein Ökosystem-Label zu; vorhanden ist nur
das erste, `github-actions` und `github_actions` fehlen beide (Kontrolle `bug`
vorhanden). `register-mcp` ist die Gegenprobe: dort existieren alle vier
deklarierten Namen mit handgeschriebener Beschreibung, die Liste ist gewollt
und vollständig.

**Dreimal falsch eingeordnet, in drei Richtungen.** Erst die Zeile für bloss
wirkungslos gehalten. Dann die gefundenen Labels für einen Widerspruch. Dann,
auf denselben Fund gestützt, einen richtigen PR geschlossen mit dem Argument,
das Label existiere ja — obwohl es existiert, *weil* die Vorgabe es anlegt.
Der dritte Fehler ist der teuerste, weil er wie eine Messung aussah.

Was die Messung **nicht** hergibt: wer die 36 Labels angelegt hat. Die
Referenz sagt, Dependabot tue es; die Objekt-IDs liegen aber so dicht
beieinander, dass sie eher aus einem Stapellauf stammen. Beides passt zum
Befund, keines ist belegt — die Herkunft blieb ungemessen.

Beim Aufräumen gilt deshalb dieselbe Frage wie bei `lotId`: Was ist die
*Vorgabe*, wenn man das Ding weglässt — nicht bloss, ob der aktuelle Wert
etwas bewirkt.

**`results[0]` ist nur so verlässlich wie die Zusicherung danach.** Pinnt die
Abfrage einen bekannten Datensatz, ist der erste Treffer eine Drift-Wache und
in Ordnung. Hängt die Zusicherung dagegen davon ab, *welche* Variante die
Quelle heute zuoberst hat, prüft der Test den Tag: am 25.8.2026 rot, weil die
neueste Zürcher Publikation zufällig Lose hatte, am 26.8. grün, ohne dass sich
etwas geändert hätte. Den Fall gezielt wählen und beide Zweige fahren.

**Und der erste Treffer einer Liste ist kein Stand — schon gar nicht, wenn man
die Antwort selbst abgeschnitten hat.** Am 19.9.2026 stand in zwei
Notion-Datenbanken als gemessener Befund, die MCP-Registry führe für
`lindas-mcp` noch 0.1.0, während Repo und PyPI auf 0.2.1 stünden. Der
Suchendpunkt liefert aber *alle* Versionen aufsteigend; gelesen worden war die
erste Zeile einer mit `head -c 800` gekürzten Antwort. Das Feld, das den Stand
markiert, stand in derselben Antwort — hinter Byte 800:

```
0.1.0  isLatest=False  published=2026-07-27T14:39:42Z
0.2.0  isLatest=False  published=2026-08-02T12:47:33Z
0.2.1  isLatest=True   published=2026-08-02T21:12:50Z
```

Die Tabelle ist die Lesung jenes Vormittags und bleibt deshalb so stehen.
Noch am selben Tag hat 0.3.0 sie überholt — wer sie für den heutigen Stand
hält, macht denselben Fehler, den der Absatz beschreibt, nur eine Ebene
höher: eine datierte Beobachtung ist kein Stand.

Der Unterschied zum Absatz davor ist die Herkunft der Verstümmelung: dort
entscheidet die Quelle, was zuoberst liegt, hier hat der Fragende sich die
Antwort selbst gekürzt. Das ist die gefährlichere Hälfte, weil die Abfrage
gegen den echten Endpunkt lief und der Befund deshalb wie eine Messung aussah.

Widerlegt hat ihn keine zweite Meinung, sondern das Job-Log von `publish.yml`
vom 2.8.2026 («Successfully published … version 0.2.1», 21:12:50 UTC), dessen
Zeitstempel sekundengenau auf dem `publishedAt` der Registry liegt. Aufgefallen
ist der Fehler auch nicht beim Nachlesen, sondern weil vor dem Nachpublizieren
die Frage stand, *warum* der Stand alt sein sollte — und drei grüne
Publish-Läufe dagegen sprachen.

- **Den Stand am Stand-Feld lesen**, nicht am Index 0: `isLatest` oder
  `version=latest`. Ein grösseres `head` hilft nicht, es verschiebt den
  Schnitt bloss.
- **Vor einer schreibenden Korrektur prüfen, warum der Ist-Zustand falsch sein
  soll.** Ein Fehlbefund, der eine Aktion auslöst, wird durch die Aktion
  bestätigt statt widerlegt: Ein `mcp-publisher publish` hätte 0.2.1 erneut
  gemeldet, und niemand hätte je erfahren, dass es schon dort war.

Was die Beobachtung *nicht* hergibt: dass die Registry ihre Versionen immer
aufsteigend liefert. Gesehen wurde eine Antwort mit drei Versionen an einem
Tag; eine Zusicherung über die Reihenfolge ist das nicht. Tragfähig ist allein
`isLatest`.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

**Bei einem blockierten PR nennt der Merge-Versuch den Blocker, jede Ableitung
rät.** `mergeable_state: blocked` bei grüner CI heisst: ein required Kontext
fehlt oder steht nicht auf grün. Welcher, sagt die Einstellung — und die sperrt
der Agent-Proxy mit HTTP 403, ein MCP-Werkzeug dafür gibt es nicht. Der Ausweg
ist nicht Indizienarbeit, sondern ein Merge-Versuch über die API:

```
PUT /repos/<owner>/<repo>/pulls/<n>/merge
405 Required status check "Codex hat diesen Head geprueft" is expected.
```

Der Name steht dort wörtlich so, wie er in der Branch Protection eingetragen
ist. Scheitert der Versuch, kostet er nichts.

Am 24./25.9.2026 über drei Repos vermessen, nachdem ein Gate-Workflow entfernt
worden war und seinen required Kontext ohne Berichterstatter zurückliess:

| Repo | eingetragener Kontext | Art |
|---|---|---|
| `register-mcp` | `Codex hat den PR angesehen` | Check-Run |
| `srgssr-mcp` | `review-abgeschlossen` | Check-Run |
| `fedlex-mcp` | `Codex hat diesen Head geprueft` | Check-Run |

**Warum Ableiten hier systematisch fehlgeht.** GitHub nimmt als Check-Run-Name
den **Job**-Namen, nicht den des Workflows. Zwei der drei Kontexte enthalten die
Zeichenfolge «codex-gate» nicht, obwohl sie aus `codex-gate.yml` stammen; wer in
den Einstellungen danach sucht, findet nichts und hält die Regel für abwesend.
Trug der Job kein `name:`, nimmt GitHub die Job-ID — daher `review-abgeschlossen`.

Zwei Fehlschlüsse sind dabei belegt, beide aus **einer** Beobachtung gezogen:

- Aus einem Commit-Status auf den required Kontext geschlossen. In `fedlex-mcp`
  stand der Status `codex-gate` auf dem Head auf `success` und blockierte
  nichts, während der fehlende Check-Run den Merge hielt. Am Kontroll-PR waren
  beide rot — dort ist nicht zu unterscheiden, welcher von beiden eingetragen
  ist. Genommen wurde der auffälligere.
- Aus einer Check-Run-Liste auf den required Kontext geschlossen. Die Liste
  zeigt, was **berichtet** wurde; eingetragen sein kann ein Name, der gerade
  gar nicht erscheint. Genau das ist der Fall, um den es geht.

**Ein Vorbehalt, der zur Methode gehört:** Die Absage nennt immer nur den
**ersten** fehlenden Kontext. Ist ein zweiter eingetragen, zeigt ihn erst der
nächste Versuch. Nach jeder Änderung an der Einstellung also erneut versuchen,
bis der Merge durchgeht oder ein neuer Name fällt.

Die Kosten der Ableitung sind gemessen: ein Arbeitstag, an dem der PR-Text den
falschen Namen trug und in den Einstellungen nach einer Zeichenfolge gesucht
wurde, die dort nicht steht.

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — Dieses Repo

**ruff: eine Quelle.** `pyproject.toml`, `dev`-Extra, `ruff==0.16.5`. Die CI
hat keinen eigenen Pin-Schritt — der Install über `ci.yml` genügt, lokal wie
dort. Eine `.pre-commit-config.yaml` gibt es nicht; wenn eine dazukommt, muss
sie dieselbe Version aus `pyproject.toml` beziehen und keine zweite nennen.
`tests/test_werkzeug_versionen.py` fällt, wenn hier eine Spanne steht oder
ein Workflow eine zweite Version setzt.

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

**Gates, wörtlich aus `ci.yml`** (Matrix: Python 3.10 / 3.11 / 3.12 / 3.13):

```
PYTHONPATH=src pytest tests/ -m "not live"
python scripts/check_ruff_pin.py
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
python scripts/check_version_sync.py
```

**Beide ruff-Gates decken dieselben drei Verzeichnisse ab, und das ist der
Punkt.** Sie liefen über `src/ tests/`, während unter `scripts/` damals zwei
Python-Dateien lagen — `record_fixtures.py` und `classify_live_run.py`,
letzteres entscheidet, ob ein roter Live-Lauf ein Issue aufmacht. Beide waren
von keinem Gate erfasst. Nachgemessen mit einer absichtlich kaputten Sonde in
`scripts/`: der alte Umfang meldete «All checks passed», der neue Exit 1.
Kein `include` unter `[tool.ruff]` setzen — das hebt die Pfadangabe der Gates
still wieder auf.

Inzwischen liegen dort vier Dateien. Die Erweiterung kam am 16.8.2026
(`d594b15`), die beiden `check_*.py` danach (`1d35b9d` am selben Abend,
`e13ec8f` am Folgetag) — beide waren also vom ersten Tag an erfasst, ohne
dass jemand etwas nachziehen musste. Das ist der Beleg für die Form: Die
Gates nennen ein Verzeichnis und keine Dateiliste.

**Das Versions-Sync-Gate gibt es jetzt.** Hier stand, es gebe keines und
`pyproject.toml` ↔ `server.json` werde «von nichts» gehalten. Beides ist
überholt: `scripts/check_version_sync.py` existiert und `ci.yml` ruft es als
fünften Schritt auf. Beim Anheben fallen die Stellen also nicht mehr
stillschweigend auseinander — von Hand zu bumpen sind sie weiterhin, das Gate
merkt es bloss.

Der Absatz hat seine eigene Lehre: Das Gate kam am 16.8.2026 (`1d35b9d`),
die Verneinung stand danach noch einen Monat hier. Eine Notiz über den Stand
der CI altert genau dann, wenn niemand sie neben die CI legt — dieselbe
Klasse wie die zweite Protokoll-Sektion in `README.md`, die `mcp>=1.28.1`
nannte, während `pyproject.toml` längst `>=2.0.0,<3` verlangte. Wer hier
etwas über Gates behauptet, liest vorher `ci.yml`.

**Was es hier tatsächlich prüft, ist weniger, als sein Name verspricht.** Der
Lauf sagt es selbst:

```
Versions-Sync OK (0.3.0; geprüft: server.json → version,
server.json → packages[0].version; keine hartkodierte Version in src/)
```

Zwei Stellen, nicht drei. Das Skript sucht auch die Versions-Badges der
READMEs (`img.shields.io/badge/version-X.Y.Z-`) — **dieses Repo hat keine**,
weder in `README.md` noch in `README.de.md`. Der Arm läuft also ins Leere. Das
ist kein Fehler, aber wer die Zeile «pyproject ↔ server.json / README / src»
im Workflow-Namen liest, hält die READMEs für abgesichert, und sie sind es
nicht. Kommt ein Badge dazu, greift der Arm ohne weiteres Zutun; bis dahin ist
eine Versionsangabe im README-Fliesstext ungeprüft.

**Die zweite Hälfte ist die schärfere.** Das Gate verbietet jede
hartkodierte Versionsnummer in `src/` — als `__version__`-Literal oder in
einem User-Agent-Token, das dem Dist-Namen entspricht. Deshalb geht
`MCPServer(version=...)` in `server.py` über `_version.__version__` und nicht
über eine Zahl: ein Literal dort wäre nicht bloss unschön, sondern rot. Der
Fallback `0.0.0+source` bleibt erlaubt, erkannt am lokalen Segment nach `+`.

**Die Matrix ist die breiteste im Portfolio: 3.10 bis 3.13**, vier Felder
statt der üblichen drei. Alle fünf Gates laufen auf allen vieren, keine
`if:`-Ausnahme. **`fail-fast: false` steht jetzt da.** Vorher galt GitHubs
Vorgabe `true`: eine rote 3.10 brach die übrigen drei ab, bevor sie etwas
sagen konnten — und 3.10 ist hier das Feld, das am ehesten allein fällt. Die
erste Frage bei einem roten Lauf ist, ob der Fehler nur eine Version trifft
oder alle vier; ein abgebrochenes Feld beantwortet sie nicht, es verschweigt
sie. Vier volle Ergebnisse kosten Rechenzeit, ein abgebrochener Lauf kostet
eine Runde.

**Live-Tests: geplanter Workflow vorhanden.** `.github/workflows/live.yml`,
`cron: "17 5 * * 1"` plus `workflow_dispatch`. Die Live-Suite ist also nicht bloss
per `-m "not live"` ausgeschlossen — DRIFT-005 ist hier erfüllt. `schedule`
greift nur auf dem Default-Branch (`main`): Änderungen am Workflow wirken erst
nach dem Merge, vorher von Hand per `workflow_dispatch`.

**Kein Gate fährt den Startpfad, und dort ist es zweimal gekracht.** Am
20.9.2026 lief der Container auf Railway in eine Neustartschleife:

```
ValueError: "Settings" object has no field "host"
```

`main()` setzte `mcp.settings.host` und `.port`. In mcp 2.x hat `Settings`
keines von beiden — die Felder sind `auth`, `debug`, `dependencies`,
`lifespan`, `log_level` und drei `warn_on_duplicate_*`. Dieselbe Entfernung
hatte schon `transport_security` getroffen; jene Zeile war in `_run_http`
bereits weg, mit erklärendem Kommentar und einem Regressionstest in
`test_cors.py`. **Der Test lag auf dem Helfer, die überlebenden Zeilen eine
Ebene höher beim Aufrufer.** Die ganze Suite baute Apps direkt über
`build_http_app`; `main()` rief kein einziger Test auf, und 177 Tests blieben
grün, während jeder HTTP-Start starb.

Die Lehre ist nicht «mcp 2.x hat Felder entfernt», sondern: **Wer eine Zeile
dieser Klasse findet, sucht ihre Geschwister im Aufrufer** — und setzt die
Naht unter Test, an der das Deployment sie ausführt. `tests/test_entry_point.py`
tut das jetzt: es patcht `uvicorn.run`, nicht `_run_http`, damit genau die
Strecke läuft, die gekracht ist.

Die Gegenprobe liegt dort auch fest: Zeilen wieder einfügen → vier
Fehlschläge; `host` oder `port` nicht an `uvicorn.run` → dieselben vier;
Loopback-Default gedreht → einer; jeder Transport in den HTTP-Zweig → die
Gegenkontrolle. Der Test, der `Settings` selbst abfragt, fällt durch **keine**
Änderung an diesem Repo — er ist eine Drift-Wache auf die Bibliothek und
steht mit dieser Einschränkung im Docstring.

Zwei Dinge, die der Crash **nicht** war: `LINDAS_MCP_ALLOWED_HOSTS` und
`ALLOWED_ORIGINS` sind auf Railway ungesetzt, der Start protokolliert beides
als Warnung und läuft weiter. Wer die Warnungen für die Ursache nimmt, sucht
am falschen Ort — sie sind Konfiguration, die auf einem öffentlich
erreichbaren Deployment trotzdem gesetzt gehört.

**Der Startbefehl war zusätzlich der falsche, ohne dass etwas rot wurde.**
`CMD ["python", "-m", "lindas_mcp.server"]` plus ein `__init__.py`, das
`.server` importiert, lädt das Modul zweimal — einmal beim Package-Import,
dann erneut als `__main__`. Das ist die `RuntimeWarning` in jedem
Container-Log, und gemessen bleiben **zwei verschiedene `MCPServer`-Objekte**
im Prozess (`s1.mcp is m2.mcp` → `False`). Bedient wurde die
`__main__`-Kopie, kaputt war nichts, die erste war Ballast mit eigenem
Modul-Zustand. `CMD ["lindas-mcp"]` importiert genau einmal. Der Test prüft
dabei nicht die Schreibweise, sondern die Naht: was `CMD` nennt, muss ein
Konsolen-Script sein, das die Distribution installiert — gelesen aus
`importlib.metadata`, nicht aus `pyproject.toml`, weil `tomllib` erst ab 3.11
in der stdlib liegt und die Matrix 3.10 mitfährt.
