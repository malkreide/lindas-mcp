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
  als Entwarnung für die gesperrte nehmen. Das ist dieselbe Asymmetrie wie
  bei der verschwundenen Codex-Meldung weiter unten.

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

Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

### Wenn Codex gar nicht erst hinsieht

Die Zeile oben unterstellt, dass es einen Befund geben *kann*. Das ist nicht
immer so, und man sieht es dem PR nicht an.

Am 21.8.2026 war das Code-Review-Kontingent zwischen 08:41 und 09:48
aufgebraucht — davor echte Reviews, danach in 30 Repos nur noch:

```
You have reached your Codex usage limits for code reviews.
```

Wie lange die Sperre dauerte, geben die Beobachtungen nur als Spanne her. Vier
Zeitpunkte sind belegt: letzter gelungener Review am 21.8. um 08:41, erste
Limit-Meldung um 09:48, letzte beobachtete Limit-Meldung am 22.8. um 11:03,
erste *andere* Meldung am 23.8. um 08:22.

Zwischen erster und letzter Limit-Meldung liegen **25 h 15 min**. Das ist der
Abstand zweier Fehlschläge, nicht die Dauer einer Sperre. Wer ihn Untergrenze
nennt, hat die durchgehende Erschöpfung schon vorausgesetzt, die er belegen
soll: Öffnete sich das Fenster zwischendurch und schloss es sich durch neue
Auslöser wieder, waren es zwei kurze Sperren und nie eine von 25 Stunden.
Untergrenze einer *einzelnen* Sperre sind die 25 h 15 min nur unter genau dieser
Annahme — und die ist unbelegt.

Nach oben trägt die Rechnung dagegen. Die längste mit den Beobachtungen
verträgliche Sperre reicht vom letzten Erfolg um 08:41 bis zur abweichenden
Meldung um 08:22, also **47 h 41 min**; länger kann keine einzelne gewesen sein.
Wer stattdessen ab der ersten Limit-Meldung rechnet, unterschlägt die 67
Minuten, in denen das Kontingent schon weg gewesen sein kann, und nennt die
Spanne zwischen zwei Beobachtungen eine Obergrenze.

Beobachtungspunkte sind keine Messreihe — die 21 Stunden vor der abweichenden
Meldung liefen ganz ohne Codex-Auslöser, dort hat niemand gemessen.

In der Zwischenzeit sind 32 PRs mit formal erfülltem Häkchen gemergt worden,
ohne dass jemand hineingesehen hat, und am 22.8. noch einmal 43.

**Vier** Gründe, warum Codex schweigt, und nur einer davon ist harmlos:

- **Kein Befund** — dann schreibt er einen gewöhnlichen Issue-Kommentar:

  ```
  Codex Review: Didn't find any major issues. Swish!
  ```

  Der Schlusssatz wechselt bei jedem Lauf («Delightful!», «Keep it up!»,
  «More of your lovely PRs please.»); stabil ist nur der Satz davor. Der
  Infokasten, den Codex unter jeden Review setzt, behauptet weiterhin eine
  Reaktion («otherwise it will react with 👍») — am 23.8. kam in sechs Repos
  die Meldung und in keinem die Reaktion. Der Kasten ist keine Quelle.
- **Der PR ist ein Draft** — darauf läuft Codex nicht an.
- **Das Kontingent ist weg** — dann schreibt er die Meldung oben.
- **Für das Repo fehlt eine Environment** — dann schreibt er:

  ```
  To use Codex here, create an environment for this repo.
  ```

Der vierte kam erst zum Vorschein, als der dritte wegfiel, und das ist kein
Zufall: Die Prüfungen liegen hintereinander. Dass es diese Reihenfolge ist und
nicht die umgekehrte, lässt sich an einem einzigen Repo ablesen — in
`swiss-public-data-mcp` bekam PR #54 am 22.8. um 10:56:55 die Kontingent-Meldung
und PR #56 am 23.8. um 08:22:20 die Environment-Meldung. Läge die
Environment-Prüfung vorn, hätte #54 sie schon am Vortag gesehen; die Environment
fehlte ja bereits. Zwei Meldungen aus demselben Repo schlagen hier jede
Vermutung über die Reihenfolge.

Praktisch heisst das: **Eine verschwundene Limit-Meldung ist keine Entwarnung.**
Sie kann bedeuten, dass das Kontingent wieder da ist — und dass jetzt etwas
anderes den Review verhindert. Belegt ist eine Prüfung erst durch ein
Review-Objekt, eine Befundlos-Meldung **oder** die Summary-Tabelle mit
`✅ Completed` (die fünfte Form, gleich unten). Wer nur das Objekt gelten lässt,
zählt jeden befundlosen Review als ungeprüft — und baut sich denselben Fehlalarm
ein, den dieser Abschnitt verhindern soll, nur in die andere Richtung.

«Kein Kommentar» heisst also nicht «geprüft und sauber». Unterscheiden lässt es
sich an der Form: Ein Review **mit** Befund ist ein Review-Objekt
(«💡 Codex Review», mit Commit-Angabe); ein Review **ohne** Befund und die
beiden Ausfallmeldungen — Kontingent wie Environment — sind gewöhnliche
Issue-Kommentare und trennen sich nur im Text. Beim Draft gibt es überhaupt
nichts, weil Codex nicht anläuft; ein kommentarloser Draft ist deshalb kein
Beleg, sondern ein nicht durchgeführter Test.

Das sind verschiedene Abfragen — `get_reviews` fürs Objekt, `get_comments` für
alles andere; wer nur eine nimmt, übersieht den Rest. Genau so ist die
Limit-Meldung zuerst durchgerutscht.

Der Kommentarzähler allein reicht ohnehin nicht: `comments: 1` kann die
Befundlos-, die Kontingent- **oder** die Environment-Meldung sein — drei
gegensätzliche Bedeutungen unter derselben Zahl. Den Text lesen, nicht die Zahl.
Und einen unbekannten vierten Text wörtlich zitieren, statt ihn in eine der
bekannten Schubladen zu zwingen: Dieser Abschnitt musste schon einmal von drei
auf vier Gründe wachsen, und die 👍-Reaktion stand hier zwei Fassungen lang als
Tatsache.

#### Die fünfte Form: eine Summary-Tabelle, die sich selbst überschreibt

Genau das ist am 19.9.2026 eingetreten, in zwei Repos unabhängig voneinander.
Codex schrieb einen Issue-Kommentar, den die vier Schubladen oben nicht kennen
— weder Befundlos-Meldung noch Ausfallmeldung, sondern eine Tabelle:

```
## Codex Review Summary

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| 📝 **Code Review** | ✅ **Completed** <relative-time …> | `bc05ec7` | Draft marked ready |
```

Das ist keine fünfte Ursache fürs Schweigen, sondern eine fünfte **Belegform**:
sie nennt den geprüften Commit und den Abschlusszeitpunkt. Deshalb steht sie
jetzt oben in der Belegliste.

**Der Kommentar wird an derselben Stelle überschrieben, nicht ergänzt.** Auf
`swiss-courts-mcp` #73 entstand er als «Running» und wurde eine Minute später
zu «Completed» editiert — dieselbe `id` (`5739967817`); auf #74 stand schon
beim Anlegen «Completed». **`created_at` sagt damit nichts über den Zustand des
Reviews.** Über alle sieben Läufe: sechsmal `created_at` ≠ `updated_at` (der
Kommentar wurde editiert), einmal identisch (#74). Die Ausnahme ist selten —
und genau deshalb gefährlich, weil sie die Regel «erst Running, dann
Completed» plausibel aussehen lässt. Wer den Kommentar einmal liest und
zwischenspeichert, sieht auf #73 für immer «Running». Den Text jedes Mal frisch
lesen und `updated_at` als Zeitpunkt der letzten Statusänderung nehmen.

Praktisch heisst das auch: **Ein Edit löst kein `issue_comment`-Ereignis aus.**
Wer auf ein Webhook wartet, wartet vergeblich — auf `lindas-mcp` #55 wanderte
`updated_at` von 06:35:44 auf 06:38:29, ohne dass ein Ereignis kam. Der
P2-Befund dort wurde nur gefunden, weil jemand gepollt hat.

**Und die Ereignisse, die kommen, kommen nicht unbedingt der Reihe nach.** Auf
`lindas-mcp` #59 traf `ready_for_review` (07:13:37) *vor* `closed/merged`
(07:13:39) ein — die Reihenfolge stimmte, die Zustellung nicht: das
Merge-Ereignis kam später an. Wer daraus «noch nicht gemergt» schliesst, hat
aus einem ausbleibenden Signal einen Zustand gemacht. Bevor der PR-Zustand die
nächste Handlung bestimmt, ihn frisch abfragen statt aus der Ereignisfolge
ableiten.

**Wie ein Befund in dieser Form aussieht** — hier war es lange ungemessen, weil
alle beobachteten Läufe sauber endeten. `lindas-mcp` #55 hat es nachgeliefert,
und die Antwort lautet: **als beides, aber die Tabelle sagt es nicht.**

| | Tabelle | `get_reviews` | `get_review_comments` |
|---|---|---|---|
| ohne Befund (6 Läufe) | `✅ Completed` | `[]` | 0 Threads |
| mit Befund (#55) | `✅ Completed` | 1 Objekt «💡 Codex Review» | 1 Thread, P2 |

Die Tabelle ist in beiden Fällen **zeichengleich** — keine zusätzliche Zeile,
kein anderer Status, kein Hinweis. Wer nur sie liest, hält einen Lauf mit
Befund für einen sauberen. Die fünfte Form belegt, **dass** geprüft wurde, und
auf welchem Commit; sie belegt nicht, **mit welchem Ergebnis**. Dafür bleibt
`get_reviews` nötig, und bei einem Treffer `get_review_comments` für die
Threads.

Was auch diese sieben Läufe **nicht** hergeben: dass «Completed» ohne
Befund-Kommentar «kein Befund» beweist. Belegt ist nur, dass in keiner
bekannten Form einer gepostet wurde. Das Fehlen der Befundlos-Meldung, die die
erste Schublade als Marker führt, bleibt unerklärt.

**Ein Merge bricht den Lauf nicht ab.** Alle sieben PRs wurden zwischen zwei und
55 Sekunden nach «ready for review» gemergt, und alle sieben Reviews liefen
danach zu Ende. Der Review ist also nicht verloren — er kommt bloss zu spät,
um noch etwas zu verhindern, und ein Befund steht dann schon im Default-Branch.
Auf #55 war es genau so.

**Wie lange man warten müsste**, aus denselben Läufen, ready bis «Completed»:

| Repo | PR | Dauer | Befund |
|---|---|---|---|
| `swiss-courts-mcp` | #74 | 63 s | — |
| `lindas-mcp` | #58 | 65 s | — |
| `lindas-mcp` | #59 | 65 s | — |
| `lindas-mcp` | #56 | 66 s | — |
| `swiss-courts-mcp` | #73 | 72 s | — |
| `lindas-mcp` | #57 | 75 s | — |
| `lindas-mcp` | #55 | **173 s** | **P2** |

Sechs liegen eng beieinander (63–75 s), einer nicht — **und der Ausreisser ist
der einzige mit Befund.** Hier stand vorher, zwei Punkte zeigten die
Grössenordnung und «wer eine Minute wartet, hat den Prüfer». Das ist widerlegt:
Eine Minute hätte sechs Läufe erwischt und genau den einen verpasst, auf den
es ankam. Ob ein Befund die Mehrzeit *verursacht*, ist
mit einer Beobachtung nicht belegt — die Vermutung liegt nahe und bleibt
Vermutung. Für die Praxis genügt die Spanne: **63 bis 173 Sekunden**, und wer
sich am unteren Ende orientiert, richtet sich nach den Läufen, die nichts zu
sagen hatten.

**Die 👍-Reaktion blieb erneut aus** — `reactions.total_count: 0` auf allen
sieben Kommentaren, während der Infokasten sie weiter behauptet. Damit steht
die Behauptung des Kastens gegen dreizehn Beobachtungen (sechs am 23.8.,
sieben am 19.9.).

Und ein befundloser Lauf ist kein Freispruch. Am 23.8. lief derselbe Text durch
42 Reviews: 36 meldeten denselben P2-Befund, 6 die Befundlos-Meldung — gleiche
Eingabe, gegenteiliges Urteil, alles in denselben neun Minuten. Ein sauberer
Lauf sagt damit etwas über den Lauf, nicht über den Text. Wer sein Häkchen
daran hängt, hängt es an einen Münzwurf.

Portfolio-weit nachsehen:

```
search_pull_requests: user:malkreide commenter:chatgpt-codex-connector[bot] updated:>=<Datum>
```

Findet nur, wo er *kommentiert* hat. Repos ohne PR-Aktivität tauchen nicht auf
— das ist kein Beleg, dass dort geprüft wurde.

Zweiter Weg, den Prüfer zu verlieren, ganz ohne Kontingentproblem: zu schnell
mergen. Am 21./22.8. lagen zwischen «ready for review» und Merge mehrfach drei
bis fünf Sekunden, am 19.9. noch sechsmal dasselbe (`swiss-courts-mcp` #73: drei
Sekunden, #74: vier; `lindas-mcp` #56: drei, #57: drei, #58: vier, #59: **zwei**
— und #55 mit 55 Sekunden immer noch zu früh). Die zwei Sekunden auf #59 sind
die bisher kürzeste beobachtete Spanne; die «drei bis fünf Sekunden» von
August sind damit keine Untergrenze mehr. Codex wird beim Umschalten von Draft
auf ready ausgelöst und braucht danach Zeit; wer sofort mergt, hat das Häkchen
gesetzt und den Review nicht abgewartet.

Wie viel Zeit, steht oben bei der fünften Form: **63 bis 173 Sekunden** von
«ready» bis «Completed», sieben Läufe. Der Lauf wird dabei nicht abgebrochen —
er endet nur, wenn niemand mehr etwas davon hat, und ein Befund steht dann
schon im Default-Branch.

Das Kontingent hängt am Konto, nicht am Repo, und Code-Reviews haben einen
eigenen Topf — nur GitHub-getriggerte Reviews zählen hinein. ChatGPT-Pläne
fahren ein rollendes Fünf-Stunden-Fenster plus Wochenlimits; welches greift,
steht im Codex-Dashboard. Welches hier griff, ist **offen**. Die Lücke oben
schliesst das Fünf-Stunden-Fenster nicht aus: Es kann sich zwischendurch
geöffnet und durch neue Auslöser wieder erschöpft haben. Das auszuschliessen
bräuchte den Nachweis, dass in der ganzen Spanne kein einziger Review durchlief
— den gibt es nicht, weil nur Fehlschläge beobachtet wurden. Eine lange Reihe
von Fehlschlägen belegt eine lange Reihe von Fehlschlägen, nicht ihre Ursache.

Zeigt das Dashboard freies Kontingent, während Reviews weiter scheitern, ist
das ein bekannter Fehler bei mehreren verbundenen Konten — dann den
GitHub-Connector in den Codex-Einstellungen trennen und neu verbinden.

Die Environment legt man unter `chatgpt.com/codex/cloud/settings/environments`
an, und zwar **je Repo**. Die Meldung sagt es selbst («for this repo»), und am
23.8. war es genau so: In `swiss-public-data-mcp` fehlte sie, dort kam kein
Review; in den übrigen Repos lief Codex am selben Morgen durch. Eine
Environment fürs Konto genügt also nicht — wer eine anlegt und den Rest für
erledigt hält, mergt weiter Ungeprüftes.

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
Versions-Sync OK (0.2.1; geprüft: server.json → version,
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
`if:`-Ausnahme. Ein `fail-fast: false` steht nicht da — eine rote 3.10 bricht
die übrigen drei ab, bevor sie etwas sagen, und 3.10 ist hier das Feld, das
am ehesten allein fällt.

**Live-Tests: geplanter Workflow vorhanden.** `.github/workflows/live.yml`,
`cron: "17 5 * * 1"` plus `workflow_dispatch`. Die Live-Suite ist also nicht bloss
per `-m "not live"` ausgeschlossen — DRIFT-005 ist hier erfüllt. `schedule`
greift nur auf dem Default-Branch (`main`): Änderungen am Workflow wirken erst
nach dem Merge, vorher von Hand per `workflow_dispatch`.

**Das PR-Template führt keine Codex-Checkliste mehr, mit Absicht.** Dort stand
«Codex-Review beantwortet oder behoben — kein offener Befund beim Merge». Das
ist eine Aussage über den Zustand *im Moment des Merges*, und genau die liess
sich hier nicht wahr ankreuzen: Codex läuft erst beim Umschalten von Draft auf
ready an und braucht danach Zeit.

Fünf der sieben Läufe in der Messreihe von Teil 1 («Die fünfte Form») stammen
aus diesem Repo — #55 bis #59. Alle fünf wurden zwischen zwei und 55 Sekunden
nach «ready» gemergt, während der Review noch lief. Auf #55 kam **116 Sekunden
nach dem Merge** ein richtiger P2-Befund (Merge 06:36:31, Review-Objekt
`submitted_at` 06:38:27).

Ein Kästchen, das eine Bedingung behauptet, die der Ablauf systematisch
verhindert, ist schlechter als keines: Es sieht nach Prüfung aus und ist keine.
Der P2 auf #55 wurde gefunden, weil jemand nach dem Merge nachgesehen hat,
nicht wegen des Häkchens.

**Was dadurch nicht wegfällt:** Teil 1 bleibt gültig — ein Codex-Review, den
es gibt, wird beantwortet oder behoben. Gestrichen ist die Behauptung, das sei
beim Merge bereits geschehen, nicht die Pflicht danach. Der Befund auf #55 ist
in #56 behoben worden, nach dem Merge.

Wer die Zusicherung zurückwill, braucht den Ablauf und nicht das Kästchen:
nach «ready» warten, bis der Review durch ist, dann mergen. Wie lange das
dauert, woran man den Abschluss überhaupt bemerkt und warum die Statustabelle
allein nichts über das *Ergebnis* sagt — das steht in Teil 1 und nur dort.

Hier stand es eine Zeitlang ein zweites Mal, mit eigenen Zahlen auf einer
anderen Bezugsgrösse (Codex-Start statt «ready») und mit dem Satz, der
Connector melde «anders, als Teil 1 es beschreibt». Beides war beim Schreiben
richtig und zwei Merges später falsch: Teil 1 beschreibt die Form inzwischen
selbst, ausführlicher und über zwei Repos gemessen. Zwei Fassungen desselben
Befunds altern unabhängig voneinander — die zweite gehört gelöscht, sobald die
erste sie einholt, und nicht gepflegt.
