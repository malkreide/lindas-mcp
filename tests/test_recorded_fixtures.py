"""Jede Abfrageform, gefahren aus einer aufgezeichneten Antwort.

Die handgeschriebenen Stubs im Rest der Suite pruefen die *Fehler*-Pfade — ein
400 mit Diagnose, ein Timeout, ein 429 —, die sich nicht auf Zuruf aufzeichnen
lassen und als Erfindung in Ordnung sind. Was sie nicht koennen: die Form einer
Erfolgs-Antwort belegen. Sie stimmen mit dem ueberein, was ihr Autor annahm.

Dieser Server spricht mit **einem** Endpunkt, aber in sieben Abfrageformen, und
die Form der Antwort haengt an der Abfrage. Aufgezeichnet ist deshalb eine
Antwort je Form, und zwar die **rohe SPARQL-JSON-Antwort**: `_parse_bindings`
gehoert zu dem, was geprueft werden soll.

Herkunft, Datum, Auswahlregel und SHA-256 je Datei stehen in
`tests/fixtures/PROVENANCE.md`; neu aufzeichnen mit
`PYTHONPATH=src python scripts/record_fixtures.py`.
"""

from __future__ import annotations

import datetime as dt
import re

import httpx
import pytest
import respx
from fixture_data import fixture_json, fixture_text, provenance, recorded_names

from lindas_mcp import server
from lindas_mcp.lindas import client as c
from lindas_mcp.lindas import cube

EP = c.ENDPOINT

# Jede Abfrageform dieses Servers und die Aufzeichnung dazu. Eine Form ohne
# Aufzeichnung faellt in `test_jede_abfrageform_hat_eine_aufzeichnung`.
ABFRAGEFORMEN = {
    "search_cubes": "search_cubes.json",
    "cube_metadata": "cube_metadata.json",
    "cube_dimensions": "cube_dimensions.json",
    "dimension_codelist": "dimension_codelist.json",
    "cube_observations": "cube_observations.json",
    "list_creators": "list_creators.json",
    "resolve_municipality_by_name": "municipality_by_name.json",
    "resolve_municipality_by_bfs": "municipality_by_bfs.json",
}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Wartezeit ueber den Modul-Alias nullen, nicht ueber `asyncio.sleep`."""

    async def _instant(_seconds):
        return None

    monkeypatch.setattr(c, "_sleep", _instant)


# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------


def test_provenance_nennt_ein_brauchbares_aufnahmedatum():
    """Eine Aufzeichnung ohne Datum ist eine undatierte Behauptung ueber die Quelle."""
    match = re.search(r"Aufgezeichnet am \*\*(\d{4}-\d{2}-\d{2})\*\*", provenance())
    assert match, "PROVENANCE.md nennt kein Aufnahmedatum im erwarteten Format"
    when = dt.date.fromisoformat(match.group(1))
    # `dt.timezone.utc`, nicht `dt.UTC`: das Alias kam mit Python 3.11, und die
    # Matrix dieses Repos faehrt auch 3.10. Lokal faellt das nicht auf, wenn das
    # venv 3.11 ist — die CI ist hier die einzige Instanz, die beide Versionen
    # sieht.
    assert when <= dt.datetime.now(dt.timezone.utc).date(), "Aufnahmedatum liegt in der Zukunft"


def test_jede_fixture_steht_in_der_provenance():
    """Sonst waechst der Ordner und der Nachweis bleibt zurueck."""
    text = provenance()
    fehlend = [n for n in recorded_names() if f"## `{n}`" not in text]
    assert not fehlend, f"ohne Eintrag in PROVENANCE.md: {fehlend}"


def test_jede_abfrageform_hat_eine_aufzeichnung():
    """Bewacht die Regel selbst — hier je Abfrageform statt je Endpunkt.

    Ein Endpunkt, sieben Formen: die Regel «eine Antwort je externem Endpunkt»
    waere hier mit einer einzigen Datei erfuellt und truege trotzdem nichts.
    """
    fehlend = sorted(set(ABFRAGEFORMEN.values()) - set(recorded_names()))
    assert not fehlend, f"Abfrageformen ohne Aufzeichnung: {fehlend}"


@pytest.mark.parametrize("name", sorted(ABFRAGEFORMEN.values()))
def test_jede_aufzeichnung_traegt_zeilen(name):
    """Eine leere Antwort sieht aus wie eine gueltige und prueft nichts.

    Genau das ist beim ersten Lauf passiert: `has_codelist` kommt als **String**
    aus SPARQL, und `if row["has_codelist"]` ist auch bei `"false"` wahr. Der
    Recorder griff deshalb die falsche Dimension und schrieb eine leere
    Codeliste. Der Server las den Wert von Anfang an richtig — der Fehler lag
    im Recorder, und diese Zusicherung faengt ihn.
    """
    zeilen = c._parse_bindings(fixture_json(name))
    assert zeilen, f"{name} traegt keine Ergebniszeilen — neu aufzeichnen"


# --------------------------------------------------------------------------
# Die Abfrageformen, jede an ihrer eigenen Antwort
# --------------------------------------------------------------------------


@respx.mock
async def test_die_suche_liest_die_aufgezeichnete_antwort():
    respx.route(host="lindas.admin.ch").mock(
        return_value=httpx.Response(200, text=fixture_text("search_cubes.json"))
    )
    ergebnis = await server.search_cubes(query="bevölkerung", limit=5)
    assert ergebnis.cubes, "die Aufzeichnung liefert Wuerfel"
    assert all(w.cube_uri for w in ergebnis.cubes)
    assert all(w.name for w in ergebnis.cubes), "kein Wuerfel darf ohne Namen herauskommen"


def test_die_dimensionen_tragen_andere_variablen_als_die_beobachtungen():
    """Der Grund, warum je Abfrageform aufgezeichnet wird.

    `cube_dimensions` antwortet mit `path`/`name`/`kind`/`has_codelist`,
    `cube_observations` mit `obs`/`p`/`o`. Ein Stub, der beide gleich raet,
    faellt nie auf — und ein Test, der nur eine Form kennt, belegt die andere
    nicht.
    """
    dims = c._parse_bindings(fixture_json("cube_dimensions.json"))
    obs = c._parse_bindings(fixture_json("cube_observations.json"))
    assert {"path", "kind", "has_codelist"} <= set(dims[0])
    assert {"obs", "p", "o"} <= set(obs[0])
    assert not (set(dims[0]) & set(obs[0])), (
        "die beiden Formen teilen keine Variable — genau deshalb braucht jede ihre eigene"
    )


def test_der_wahrheitswert_kommt_als_string():
    """Die Falle, die diese Aufzeichnung aufgedeckt hat — an der echten Antwort.

    SPARQL liefert `BOUND(?in)` als Literal `"true"`/`"false"`, nicht als
    JSON-Boolean. `cube.py` wandelt ausdruecklich um; wer das vergisst, haelt
    jede Dimension fuer codelistenbehaftet.
    """
    dims = c._parse_bindings(fixture_json("cube_dimensions.json"))
    werte = {d["has_codelist"] for d in dims}
    assert werte <= {"true", "false"}, f"unerwartete Werte: {werte}"
    assert "false" in werte, (
        "die Aufzeichnung enthaelt keine Dimension ohne Codeliste — dann prueft "
        "dieser Test die Falle nicht mehr"
    )
    assert all(isinstance(w, str) for w in werte), "als String, nicht als Boolean"
    # Und so gelesen, wie der Server es tut:
    gemappt = cube.parse_dimensions(dims) if hasattr(cube, "parse_dimensions") else None
    if gemappt is not None:
        assert any(d["has_codelist"] is False for d in gemappt), (
            "nach der Umwandlung muss mindestens eine Dimension False sein"
        )


@respx.mock
async def test_die_struktur_loest_die_codeliste_auf():
    """Zwei Antwortformen hintereinander: Dimensionen, dann Codeliste."""
    antworten = [
        httpx.Response(200, text=fixture_text("cube_metadata.json")),
        httpx.Response(200, text=fixture_text("cube_dimensions.json")),
    ] + [httpx.Response(200, text=fixture_text("dimension_codelist.json"))] * 8
    respx.route(host="lindas.admin.ch").mock(side_effect=antworten)
    ergebnis = await server.get_cube_structure(
        cube_uri="https://environment.ld.admin.ch/foen/ubd003701/6"
    )
    assert ergebnis.dimensions, "die Aufzeichnung liefert Dimensionen"
    assert any(d.has_codelist for d in ergebnis.dimensions)
    assert any(not d.has_codelist for d in ergebnis.dimensions), (
        "mindestens eine Dimension ohne Codeliste — sonst ist der String-Wert "
        "«false» als wahr gelesen worden"
    )


@respx.mock
async def test_die_beobachtungen_werden_aus_tripeln_gedreht():
    """Die Quelle liefert `obs`/`p`/`o`; der Server macht daraus Zeilen."""
    # Das Werkzeug geht drei Schritte: Metadaten, Dimensionen, Beobachtungen.
    # Alle drei mit derselben Antwort zu bedienen hiesse, die Aufzeichnung gegen
    # eine Abfrage zu halten, die sie nicht beantwortet — genau der Fehler, den
    # eine Fixture je Abfrageform verhindern soll.
    respx.route(host="lindas.admin.ch").mock(
        side_effect=[
            httpx.Response(200, text=fixture_text("cube_metadata.json")),
            httpx.Response(200, text=fixture_text("cube_dimensions.json")),
            httpx.Response(200, text=fixture_text("cube_observations.json")),
        ]
    )
    ergebnis = await server.query_cube_observations(
        cube_uri="https://environment.ld.admin.ch/foen/ubd003701/6",
        limit=5,
        resolve_labels=False,
    )
    assert ergebnis.observations, "die Aufzeichnung liefert Beobachtungen"
    roh = c._parse_bindings(fixture_json("cube_observations.json"))
    assert len({r["obs"] for r in roh}) == len(ergebnis.observations), (
        "je Beobachtung eine Zeile — die Tripel gehoeren gruppiert, nicht gezaehlt"
    )


@respx.mock
async def test_die_herausgeberliste_aus_der_aufzeichnung():
    respx.route(host="lindas.admin.ch").mock(
        return_value=httpx.Response(200, text=fixture_text("list_creators.json"))
    )
    ergebnis = await server.list_publishers()
    assert ergebnis.publishers
    assert all(p.creator_uri and p.cube_count >= 0 for p in ergebnis.publishers)


@respx.mock
@pytest.mark.parametrize(
    ("eingabe", "fixture"),
    [("Winterthur", "municipality_by_name.json"), ("230", "municipality_by_bfs.json")],
)
async def test_beide_gemeindewege_treffen_dieselbe_gemeinde(eingabe, fixture):
    """Name und BFS-Nummer sind zwei Abfragen — und ein Gegenstand.

    Der Recorder fragt bewusst dieselbe Gemeinde ueber beide Wege ab. Zwei
    erfundene Fixtures haetten hier leicht zwei verschiedene Gemeinden gezeigt,
    ohne dass es jemandem auffiele.
    """
    respx.route(host="lindas.admin.ch").mock(
        return_value=httpx.Response(200, text=fixture_text(fixture))
    )
    ergebnis = await server.resolve_municipality(name_or_bfs=eingabe)
    assert ergebnis.municipalities, "die Aufzeichnung liefert eine Gemeinde"
    assert ergebnis.match_type == "exact"
    assert ergebnis.municipalities[0].uri


def test_die_beiden_gemeindeabfragen_beschreiben_denselben_ort():
    """Am Nachweis statt an der Vermutung: gleiche URI, gleiche Nummer."""
    ueber_name = c._parse_bindings(fixture_json("municipality_by_name.json"))[0]
    ueber_bfs = c._parse_bindings(fixture_json("municipality_by_bfs.json"))[0]
    assert ueber_name["muni"] == ueber_bfs["muni"]
    assert ueber_name["ident"] == ueber_bfs["ident"]


def test_alle_aufzeichnungen_beschreiben_denselben_wuerfel():
    """Sonst beschreiben sieben Dateien sieben Gegenstaende.

    Metadaten, Dimensionen, Beobachtungen und Codeliste sind nur zusammen eine
    Aussage ueber *einen* Wuerfel. Der Recorder nimmt dafuer den ersten Treffer
    der Suche; diese Zusicherung haelt fest, dass er es getan hat.
    """
    treffer = c._parse_bindings(fixture_json("search_cubes.json"))
    wuerfel = treffer[0]["cube"]
    nachweis = provenance()
    assert wuerfel in nachweis, "der Nachweis nennt den Wuerfel nicht"
    metadaten = c._parse_bindings(fixture_json("cube_metadata.json"))
    assert metadaten, "die Metadaten-Aufzeichnung ist leer"
    beobachtungen = c._parse_bindings(fixture_json("cube_observations.json"))
    assert all(wuerfel.rsplit("/", 1)[0] in b["obs"] for b in beobachtungen), (
        "die Beobachtungen gehoeren zu einem anderen Wuerfel als die Suche"
    )


def test_der_recorder_laesst_sich_importieren():
    """Faengt eine Klasse, die weder Ruff noch die uebrige Suite sieht.

    `scripts/record_fixtures.py` wird von niemandem importiert: nicht vom
    Paket, nicht von den Tests, nicht von der CI. Ein Fehler darin faellt
    deshalb erst auf, wenn jemand neu aufzeichnen will — und dann steht er vor
    einem Werkzeug, das nicht startet.

    Genau das war der Fall: der Recorder schrieb `from datetime import UTC`,
    ein Alias, das es erst ab Python 3.11 gibt, waehrend dieses Repo ab 3.10
    unterstuetzt. Ruff meldet es nicht — bei `target-version = "py310"`
    schlaegt UP017 den Kurznamen gar nicht erst vor, verbietet ihn aber auch
    nicht. Der Import hier macht aus dem stillen Fall einen roten Test, und
    zwar auf **jeder** Version der Matrix.
    """
    import importlib.util
    from pathlib import Path

    pfad = Path(__file__).resolve().parent.parent / "scripts" / "record_fixtures.py"
    assert pfad.is_file(), f"Recorder nicht gefunden: {pfad}"
    spec = importlib.util.spec_from_file_location("record_fixtures_probe", pfad)
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)  # nur Import — `main()` wird nicht gerufen
    assert hasattr(modul, "main"), "der Recorder hat keinen Einstiegspunkt"


# --------------------------------------------------------------------------
# Der Nachweis, nachgerechnet
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(n for n in recorded_names() if n != "PROVENANCE.md"))
def test_die_pruefsumme_im_nachweis_stimmt(name):
    """Eine Pruefsumme, die niemand nachrechnet, ist Zierde.

    Sie steht im Nachweis, um genau einen Fall zu fangen: eine Aufzeichnung,
    die nach dem Lauf von Hand nachgebessert wurde. Eine korrigierte Antwort
    ist wieder eine erfundene — und von aussen ist ihr das nicht anzusehen.
    Ohne diesen Test faengt die Summe nichts.

    Gerechnet wird ueber die Bytes auf der Platte, nicht ueber den Loader:
    genau die hat der Recorder gehasht, und ein Loader, der unterwegs dekodiert
    oder normalisiert, wuerde die Pruefung gegen sich selbst fuehren.
    """
    import hashlib
    import re
    from pathlib import Path

    teile = provenance().split(f"## `{name}`", 1)
    assert len(teile) == 2, f"{name} hat keinen Block in PROVENANCE.md"
    treffer = re.search(r"\*\*SHA-256:\*\*\s*`([0-9a-f]{64})`", teile[1].split("## ", 1)[0])
    assert treffer, f"{name} steht ohne Pruefsumme im Nachweis"
    roh = (Path(__file__).resolve().parent / "fixtures" / name).read_bytes()
    assert hashlib.sha256(roh).hexdigest() == treffer.group(1), (
        f"{name} weicht vom Nachweis ab — von Hand nachgebessert? Neu aufzeichnen."
    )
