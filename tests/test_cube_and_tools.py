"""Layer-2 (cube) and tool tests, plus live probes excluded from CI.

The two mechanisms most likely to break — version deduplication and
code-to-label resolution — get dedicated unit tests. The observationSet
indirection (fundstück 6) gets a live test, because that was a structural
assumption a mock cannot validate.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from lindas_mcp import server
from lindas_mcp.lindas import client as c
from lindas_mcp.lindas import cube, queries

EP = c.ENDPOINT


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _instant(_seconds):
        return None

    monkeypatch.setattr(c, "_sleep", _instant)


def _results(*rows: dict) -> dict:
    bindings = [{k: {"value": v} for k, v in row.items()} for row in rows]
    return {"head": {"vars": []}, "results": {"bindings": bindings}}


def _such_und_zaehl(such_rows: dict, *, zaehl_n: int | None = None, zaehl_status: int = 200):
    """respx handler that answers the search query and the count query apart.

    Returns ``(handler, gesehen)``; ``gesehen`` collects "search" / "count" in
    call order, so a test can assert that the count query was issued — or, just
    as important, that it was NOT. A second round trip on every search would be
    a cost the caller never asked for, and only an assertion on the absence
    catches it.
    """
    gesehen: list[str] = []

    def handler(request):
        # Decode the query out of the URL (GET) or body (POST); the raw URL
        # keeps `COUNT(DISTINCT` percent-encoded, which breaks matching.
        from urllib.parse import unquote_plus

        q = unquote_plus(str(request.url)) + request.content.decode("utf-8", "ignore")
        if "COUNT(DISTINCT ?cube)" in q:
            gesehen.append("count")
            if zaehl_status != 200:
                return httpx.Response(zaehl_status, text="der Store mag nicht")
            return httpx.Response(200, json=_results({"n": str(zaehl_n)}))
        gesehen.append("search")
        return httpx.Response(200, json=such_rows)

    return handler, gesehen


def _cubes(n: int, *, ab: int = 0) -> dict:
    """`n` rows, each a distinct logical cube, all published."""
    return _results(
        *[
            {
                "cube": f"https://x/c{i}/cube/2024-1",
                "name": f"C{i}",
                "version": "2024.1",
                "status": "https://ld/Published",
            }
            for i in range(ab, ab + n)
        ]
    )


# --------------------------------------------------------------------------
# Version deduplication
# --------------------------------------------------------------------------


def test_base_cube_uri_strips_version_suffix():
    assert (
        cube._base_cube_uri("https://x.ld.admin.ch/foen/nfi/nfi_C-501/cube/2024-1")
        == "https://x.ld.admin.ch/foen/nfi/nfi_C-501"
    )
    assert (
        cube._base_cube_uri("https://x.ld.admin.ch/foen/warnung/1")
        == "https://x.ld.admin.ch/foen/warnung"
    )


@respx.mock
async def test_search_keeps_only_newest_version_per_cube():
    rows = _results(
        {
            "cube": "https://x/c/cube/2023-1",
            "name": "C",
            "version": "2023.1",
            "status": "Published",
        },
        {
            "cube": "https://x/c/cube/2024-1",
            "name": "C",
            "version": "2024.1",
            "status": "Published",
        },
        {
            "cube": "https://x/c/cube/2023-2",
            "name": "C",
            "version": "2023.2",
            "status": "Published",
        },
    )
    respx.get(EP).mock(return_value=httpx.Response(200, json=rows))
    async with c.build_client() as http:
        result = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=10, latest_only=True
        )
    assert len(result["cubes"]) == 1
    assert result["cubes"][0]["version"] == "2024.1"
    # Three versions collapsed to one cube, and the store was nowhere near the
    # LIMIT, so the total is the collapsed count — not the three rows that came in.
    assert result["total_matched"] == 1
    assert result["truncated"] is False


@respx.mock
async def test_search_without_dedup_returns_all_versions():
    rows = _results(
        {"cube": "https://x/c/cube/2023-1", "version": "2023.1", "status": "Published"},
        {"cube": "https://x/c/cube/2024-1", "version": "2024.1", "status": "Published"},
    )
    respx.get(EP).mock(return_value=httpx.Response(200, json=rows))
    async with c.build_client() as http:
        result = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=10, latest_only=False
        )
    assert len(result["cubes"]) == 2
    assert result["total_matched"] == 2
    assert result["truncated"] is False


# --------------------------------------------------------------------------
# Completeness: truncated / total_matched (FID)
#
# `returned` alone cannot tell "that is all there is" from "that is page one",
# and a caller who cannot tell stops at the page it got. Every branch of that
# decision gets a test here, including the two where the answer is "unknown" —
# those are the ones an implementation gets silently wrong.
# --------------------------------------------------------------------------


@respx.mock
async def test_nicht_gedeckelt_heisst_exaktes_total_und_kein_zweiter_roundtrip():
    """The cheap route. Fewer rows than asked for means every match was seen, so
    the total is free — and the count query must not be issued at all."""
    handler, gesehen = _such_und_zaehl(_cubes(3))
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=5, latest_only=True
        )
    assert r["total_matched"] == 3
    assert r["truncated"] is False
    assert len(r["cubes"]) == 3
    assert gesehen == ["search"], f"ein zweiter Roundtrip ohne Not: {gesehen}"


@respx.mock
async def test_mehr_treffer_als_limit_ist_truncated_mit_exaktem_total():
    """Truncated and exact at the same time: the store was not capped, so the
    total is known even though the page is cut. `limit` alone would not say it."""
    handler, gesehen = _such_und_zaehl(_cubes(5))
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=2, latest_only=True
        )
    assert len(r["cubes"]) == 2
    assert r["total_matched"] == 5
    assert r["truncated"] is True
    assert gesehen == ["search"]


@respx.mock
async def test_genau_limit_treffer_sind_vollstaendig_und_kosten_keine_zaehlung():
    """The `+ 1` of the over-fetch, as a test — without it nothing below holds.

    Exactly as many matches as `limit`. That is the one case where a full page
    and an exhausted result set are indistinguishable, and the extra row is what
    separates them: `fetch` is 4, four rows were allowed, three came back, so
    there is no fifth and the answer is complete.

    Drop the `+ 1` and `fetch` becomes 3, three rows look like a cap, and all
    three of these assertions move at once — the total climbs to the count's
    answer, `truncated` flips to True, and a second round trip is spent finding
    that out. The count is given a deliberately wrong 99 here so that reaching
    for it cannot accidentally produce the right number.
    """
    handler, gesehen = _such_und_zaehl(_cubes(3), zaehl_n=99)
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=3, latest_only=False
        )
    assert len(r["cubes"]) == 3
    assert r["total_matched"] == 3, "das Total kam aus der Zaehlung statt aus der Pipeline"
    assert r["truncated"] is False, "eine volle Seite wurde fuer abgeschnitten gehalten"
    assert gesehen == ["search"], f"unnoetige Zaehlabfrage: {gesehen}"


@respx.mock
async def test_eine_zeile_unter_dem_deckel_bleibt_exakt_zaehlbar():
    """The same mechanism on the dedup branch, where the margin is wider.

    `limit=2` asks for `2*4 + 1 = 9` rows and eight arrive — one short, so every
    match was seen and the total is exact at 8 even though only two are returned.
    Without the `+ 1` the ask is eight, eight arrive, the page looks capped, and
    an exactly known 8 degrades to None: the caller loses a number that was
    available, on the branch where no second query can recover it.
    """
    handler, gesehen = _such_und_zaehl(_cubes(8))
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=2, latest_only=True
        )
    assert len(r["cubes"]) == 2
    assert r["total_matched"] == 8, "acht sichtbare Treffer wurden zu «unbekannt»"
    assert r["truncated"] is True
    assert gesehen == ["search"]


@respx.mock
async def test_gedeckelt_mit_latest_only_laesst_total_offen_statt_versionen_zu_melden():
    """The design decision, as a test. With `latest_only=True` the number the
    store can give counts cube VERSIONS while this layer returns collapsed cubes
    — measured live 2026-09-20, «wald»: 127 versions, 35 cubes. Reporting 127
    would tell a caller it is missing 107 cubes when at most 15 exist to find, so
    the total stays None and `truncated` carries the message. No count query is
    issued either, because its answer would not be comparable.
    """
    handler, gesehen = _such_und_zaehl(_cubes(9))  # limit 2 -> fetch 2*4+1 = 9
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=2, latest_only=True
        )
    assert len(r["cubes"]) == 2
    assert r["total_matched"] is None
    assert r["truncated"] is True
    assert gesehen == ["search"], f"eine unvergleichbare Zaehlung wurde geholt: {gesehen}"


@respx.mock
async def test_gedeckelt_ohne_latest_only_holt_das_total_per_zaehlabfrage():
    """The one case the cheap route cannot answer and the count query can: rows
    are cube versions here, which is exactly what `count_cubes` counts."""
    handler, gesehen = _such_und_zaehl(_cubes(3), zaehl_n=47)  # limit 2 -> fetch 3
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=2, latest_only=False
        )
    assert len(r["cubes"]) == 2
    assert r["total_matched"] == 47
    assert r["truncated"] is True
    assert gesehen == ["search", "count"], gesehen


@respx.mock
async def test_ein_exaktes_total_schlaegt_den_deckel_des_stores():
    """The load-bearing case for deriving `truncated` from the total.

    The store WAS capped, so «capped, therefore truncated» would say True. But
    the status filter threw two of the three rows away, and the count says there
    are exactly three published matches in total — all three of which are in
    `cubes`. Nothing was withheld, so `truncated` is False.

    Without this test both formulas pass everything else, and the naive one sends
    a caller paging after a result set it already holds in full.
    """
    rows = _results(
        {"cube": "https://x/a/cube/2024-1", "name": "a", "status": "https://ld/Published"},
        {"cube": "https://x/b/cube/2024-1", "name": "b", "status": "https://ld/Draft"},
        {"cube": "https://x/c/cube/2024-1", "name": "c", "status": "https://ld/Expired"},
    )
    handler, gesehen = _such_und_zaehl(rows, zaehl_n=1)  # limit 2 -> fetch 3 -> gedeckelt
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=2, latest_only=False
        )
    assert [h["cube"] for h in r["cubes"]] == ["https://x/a/cube/2024-1"]
    assert r["total_matched"] == 1
    assert r["truncated"] is False, "der Deckel des Stores hat das exakte Total ueberstimmt"
    assert gesehen == ["search", "count"]


@respx.mock
async def test_eine_gescheiterte_zaehlung_kostet_das_total_und_nicht_die_treffer():
    """The count is a nicety, the hits are the deliverable. A store that refuses
    to count must not turn a successful search into an error — it must turn
    `total_matched` into None, which is what None is for."""
    handler, gesehen = _such_und_zaehl(_cubes(3), zaehl_status=500)
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=2, latest_only=False
        )
    assert len(r["cubes"]) == 2, "die Treffer sind mit der Zaehlung verlorengegangen"
    assert r["total_matched"] is None
    # Unknown must read as "there may be more", never as "that was all".
    assert r["truncated"] is True
    assert "count" in gesehen


@respx.mock
async def test_ein_cube_ohne_status_zaehlt_mit():
    """The Python half of the status rule. `search` keeps a row whose
    `creativeWorkStatus` is absent (`or "status" not in r`), so such a cube is a
    hit and counts towards the total. Measured live: eight cubes in the store
    carry no status at all, and a rule that dropped them would be short by
    exactly those — silently, because the count would agree with the omission.
    """
    rows = _results(
        {"cube": "https://x/mit/cube/2024-1", "name": "mit", "status": "https://ld/Published"},
        {"cube": "https://x/ohne/cube/2024-1", "name": "ohne"},  # kein status-Feld
    )
    handler, _ = _such_und_zaehl(rows)
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        r = await cube.search(
            http, query="c", language="de", creator_uri=None, limit=10, latest_only=False
        )
    assert {h["cube"] for h in r["cubes"]} == {
        "https://x/mit/cube/2024-1",
        "https://x/ohne/cube/2024-1",
    }
    assert r["total_matched"] == 2


def test_die_zaehlvorlage_spiegelt_den_statusfilter_ueber_bound():
    """The SPARQL half of the same rule, pinned as text.

    Measured live on 2026-09-20 for the term «e»: a strict
    `FILTER(STRENDS(STR(?status), "Published"))` counted 1520, the `!BOUND` form
    1528. The eight-cube gap is the cubes that carry no status, which
    `cube.search` keeps. This is a pin on a measured decision, not a behavioural
    test — reproducing the 1520/1528 split needs the real store, and the live
    test below is where that half lives. It exists so that «simplifying» the
    filter away turns red instead of quietly shrinking every total by eight.
    """
    q = queries.count_cubes("wald", "de", None)
    assert "COUNT(DISTINCT ?cube)" in q
    assert "!BOUND(?status)" in q
    # Same anchor and same term filter as the search it has to be comparable to.
    assert "?cube a cube:Cube" in q
    assert 'CONTAINS(LCASE(STR(?name)), "wald")' in q


def test_die_zaehlvorlage_traegt_den_creator_filter_mit():
    """A count that ignored `creator_uri` would answer a wider question than the
    search asked — and would read as «you are missing cubes» when the caller had
    deliberately narrowed to one federal body."""
    ohne = queries.count_cubes("wald", "de", None)
    mit = queries.count_cubes("wald", "de", "https://ld.admin.ch/office/XI.1")
    assert "dcterms:creator" not in ohne
    assert "?cube dcterms:creator <https://ld.admin.ch/office/XI.1> ." in mit


# --------------------------------------------------------------------------
# Code-to-label resolution (the two-phase heart)
# --------------------------------------------------------------------------


@respx.mock
async def test_observations_resolve_codes_to_labels():
    """A coded region value must come back as its human label."""

    def handler(request):
        # Decode the SPARQL query out of the URL (GET) or body (POST); the raw
        # URL string keeps `cube:Cube` as `cube%3ACube`, which breaks matching.
        from urllib.parse import unquote_plus

        q = unquote_plus(str(request.url)) + request.content.decode("utf-8", "ignore")
        if "observationConstraint" in q and "sh:in ?list" in q:
            # codelist for the region dimension
            return httpx.Response(
                200,
                json=_results(
                    {"value": "https://x/region/1805", "ident": "1805", "label": "Alpennordhang"}
                ),
            )
        if "observationConstraint" in q:
            # structure: one key dimension with a codelist
            return httpx.Response(
                200,
                json=_results(
                    {
                        "path": "https://x/region",
                        "name": "Warnregion",
                        "kind": "https://cube.link/KeyDimension",
                        "has_codelist": "true",
                    }
                ),
            )
        if "cube:Cube" in q and "schema:name" in q and "COUNT" not in q:
            return httpx.Response(200, json=_results({"name": "Warnungen"}))
        if "observationSet" in q:
            return httpx.Response(
                200,
                json=_results(
                    {
                        "obs": "https://x/obs/1",
                        "p": "https://x/region",
                        "o": "https://x/region/1805",
                    }
                ),
            )
        return httpx.Response(200, json=_results())

    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    async with c.build_client() as http:
        data = await cube.get_observations(
            http, cube_uri="https://x/c", language="de", limit=10, resolve_labels=True
        )
    assert data["returned"] == 1
    # keyed by dimension name, value resolved to label
    assert data["observations"][0]["Warnregion"] == "Alpennordhang"


@respx.mock
async def test_beobachtungen_loesen_labels_ohne_vorherigen_strukturaufruf_auf():
    """Die Zusicherung, auf der die `instructions` des Servers stehen.

    Ein Codex-Review auf PR #55 hat belegt, dass der Text dort das Gegenteil
    behauptete: der Client muesse erst `get_cube_structure` rufen, sonst
    bekaeme er «codes you cannot interpret». Nachgemessen stimmt das nicht —
    `cube.get_observations` holt die Struktur selbst und laedt jede Codeliste,
    bevor es antwortet. Ein Strukturaufruf davor wiederholt nur Abfragen.

    Dieser Test faehrt deshalb den Werkzeugpfad OHNE jeden vorherigen Aufruf
    und zaehlt zugleich mit, was an den Endpunkt geht: die Strukturabfrage
    muss darin vorkommen, sonst belegte der Test nur das Label und nicht, wo
    es herkommt. Faellt er, ist die Aussage in `SERVER_INSTRUCTIONS` und in
    beiden READMEs wieder falsch.
    """
    from urllib.parse import unquote_plus

    gesehen: list[str] = []

    def handler(request):
        q = unquote_plus(str(request.url)) + request.content.decode("utf-8", "ignore")
        gesehen.append(q)
        if "observationConstraint" in q and "sh:in ?list" in q:
            return httpx.Response(
                200,
                json=_results(
                    {"value": "https://x/region/1805", "ident": "1805", "label": "Alpennordhang"}
                ),
            )
        if "observationConstraint" in q:
            return httpx.Response(
                200,
                json=_results(
                    {
                        "path": "https://x/region",
                        "name": "Warnregion",
                        "kind": "https://cube.link/KeyDimension",
                        "has_codelist": "true",
                    }
                ),
            )
        if "cube:Cube" in q and "schema:name" in q and "COUNT" not in q:
            return httpx.Response(200, json=_results({"name": "Warnungen"}))
        if "observationSet" in q:
            return httpx.Response(
                200,
                json=_results(
                    {
                        "obs": "https://x/obs/1",
                        "p": "https://x/region",
                        "o": "https://x/region/1805",
                    }
                ),
            )
        return httpx.Response(200, json=_results())

    respx.route(host="lindas.admin.ch").mock(side_effect=handler)

    ergebnis = await server.query_cube_observations(cube_uri="https://x/c", limit=10)

    assert ergebnis.labels_resolved is True
    assert ergebnis.observations[0]["Warnregion"] == "Alpennordhang", (
        "ohne vorherigen get_cube_structure-Aufruf kam kein Label zurueck"
    )
    assert any("observationConstraint" in q for q in gesehen), (
        "die Struktur wurde nicht im Werkzeug selbst geholt — dann saehe der "
        "Aufrufer sie nirgends, und der Doppelaufruf waere doch noetig"
    )


@respx.mock
async def test_die_struktur_gibt_die_codeliste_nicht_her():
    """Der zweite Teil desselben Befunds, und der ueberraschendere.

    Selbst wer `get_cube_structure` vorher ruft, bekommt die Codeliste nicht:
    `Dimension` fuehrt `has_codelist` als Flag und keine Eintraege. Ein
    Strukturaufruf taugt also auch dann nicht als Decodierhilfe, wenn jemand
    `resolve_labels=False` faehrt. Ohne diesen Fall liesse sich der Text
    wieder auf «ruf erst die Struktur, dann kannst du decodieren» drehen.
    """
    from urllib.parse import unquote_plus

    def handler(request):
        q = unquote_plus(str(request.url)) + request.content.decode("utf-8", "ignore")
        if "observationConstraint" in q:
            return httpx.Response(
                200,
                json=_results(
                    {
                        "path": "https://x/region",
                        "name": "Warnregion",
                        "kind": "https://cube.link/KeyDimension",
                        "has_codelist": "true",
                    }
                ),
            )
        if "cube:Cube" in q and "schema:name" in q and "COUNT" not in q:
            return httpx.Response(200, json=_results({"name": "Warnungen"}))
        return httpx.Response(200, json=_results())

    respx.route(host="lindas.admin.ch").mock(side_effect=handler)

    struktur = await server.get_cube_structure(cube_uri="https://x/c")
    dimension = struktur.dimensions[0]

    assert dimension.has_codelist is True
    gefuehrte_felder = set(dimension.model_dump())
    assert gefuehrte_felder == {"path", "name", "kind", "has_codelist"}, gefuehrte_felder


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


@respx.mock
async def test_search_cubes_tool_envelope():
    respx.get(EP).mock(
        return_value=httpx.Response(
            200,
            json=_results(
                {
                    "cube": "https://x/c/1",
                    "name": "Waldbrand",
                    "version": "1",
                    "status": "https://ld/Published",
                }
            ),
        )
    )
    result = await server.search_cubes(query="wald", limit=5)
    assert result.returned == 1
    assert result.cubes[0].name == "Waldbrand"
    assert result.cubes[0].status == "Published"
    assert result.provenance == "live_sparql"
    assert "LINDAS" in result.source


@respx.mock
async def test_search_cubes_tool_traegt_die_vollstaendigkeitsangabe_nach_aussen():
    """The fields have to survive the model boundary, not just exist in layer 2.

    `truncated` is declared without a default on purpose: a default of False
    would be a claim of completeness that any future code path could inherit
    without having checked. If this assertion ever reads False where the layer
    said True, the wiring dropped it — which is the failure that cannot be seen
    from the outside.
    """
    handler, _ = _such_und_zaehl(_cubes(3))
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    voll = await server.search_cubes(query="wald", limit=5)
    assert voll.returned == 3
    assert voll.total_matched == 3
    assert voll.truncated is False

    handler, _ = _such_und_zaehl(_cubes(21))  # limit 5 -> fetch 5*4+1 = 21, gedeckelt
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    knapp = await server.search_cubes(query="wald", limit=5)
    assert knapp.returned == 5
    assert knapp.truncated is True
    assert knapp.total_matched is None


@respx.mock
async def test_ein_leeres_ergebnis_ist_nicht_abgeschnitten():
    """The counter-control on the "errs towards True" rule: nothing matched is a
    complete answer, and calling it truncated would send a caller widening a
    search that has nothing to widen towards."""
    handler, _ = _such_und_zaehl(_results())
    respx.route(host="lindas.admin.ch").mock(side_effect=handler)
    leer = await server.search_cubes(query="zzzz-nonexistent")
    assert leer.returned == 0
    assert leer.total_matched == 0
    assert leer.truncated is False
    assert leer.match_type == "none"


@respx.mock
async def test_resolve_municipality_by_bfs_number():
    respx.get(EP).mock(
        return_value=httpx.Response(
            200,
            json=_results(
                {"muni": "https://ld.admin.ch/municipality/261", "name": "Zürich", "ident": "261"}
            ),
        )
    )
    result = await server.resolve_municipality(name_or_bfs="261")
    assert result.municipalities[0].bfs_number == "261"
    assert result.municipalities[0].name == "Zürich"


@respx.mock
async def test_run_sparql_caps_rows():
    many = _results(*[{"s": f"u{i}"} for i in range(600)])
    respx.get(EP).mock(return_value=httpx.Response(200, json=many))
    result = await server.run_sparql(query="SELECT ?s WHERE { ?s a <https://cube.link/Cube> }")
    assert result.row_count == server.RUN_SPARQL_ROW_CAP
    assert "500" in result.note


@respx.mock
async def test_api_status_reports_failure_gracefully():
    respx.get(EP).mock(side_effect=httpx.ConnectTimeout("down"))
    status = await server.api_status()
    assert status.reachable is False
    assert "unreachable" in status.note.lower()


# --------------------------------------------------------------------------
# Not-found heuristics (ARCH-003)
# --------------------------------------------------------------------------


@respx.mock
async def test_search_cubes_reports_no_match_with_suggestion():
    respx.get(EP).mock(return_value=httpx.Response(200, json=_results()))
    result = await server.search_cubes(query="zzzz-nonexistent")
    assert result.returned == 0
    assert result.match_type == "none"
    assert result.suggestion and "list_publishers" in result.suggestion


@respx.mock
async def test_resolve_municipality_reports_no_match():
    respx.get(EP).mock(return_value=httpx.Response(200, json=_results()))
    result = await server.resolve_municipality(name_or_bfs="Nowhere")
    assert result.returned == 0
    assert result.match_type == "none"
    assert result.suggestion


# --------------------------------------------------------------------------
# Error masking (OBS-002) and pooled client (SDK-001)
# --------------------------------------------------------------------------


async def test_mask_errors_masks_unexpected_but_passes_known():
    @server.mask_errors
    async def boom_unexpected():
        raise KeyError("secret internal detail")

    @server.mask_errors
    async def boom_known():
        raise c.SparqlError("MALFORMED QUERY at line 3")

    with pytest.raises(RuntimeError) as exc:
        await boom_unexpected()
    # The raw internal detail must not leak into the surfaced message.
    assert "secret internal detail" not in str(exc.value)

    # Known, LLM-safe errors propagate unchanged.
    with pytest.raises(c.SparqlError):
        await boom_known()


async def test_client_session_prefers_shared_client():
    sentinel = object()
    c.set_shared_client(sentinel)  # type: ignore[arg-type]
    try:
        async with c.client_session() as http:
            assert http is sentinel
    finally:
        c.set_shared_client(None)
    assert c.get_shared_client() is None


# --------------------------------------------------------------------------
# Tool-definition integrity (SEC-022)
# --------------------------------------------------------------------------


async def test_tool_manifest_matches_committed_lock():
    """SEC-022: the live tool definitions must match tool-definitions.lock.json
    so a silent rug-pull fails CI until the lock is regenerated and reviewed."""
    import json
    from pathlib import Path

    lock_path = Path(__file__).resolve().parent.parent / "tool-definitions.lock.json"
    assert lock_path.exists(), "tool-definitions.lock.json is missing"
    committed = json.loads(lock_path.read_text(encoding="utf-8"))
    live = await server.tool_manifest()
    assert live["combined_sha256"] == committed["combined_sha256"], (
        "Tool definitions changed. Regenerate tool-definitions.lock.json and "
        "note the change in CHANGELOG.md (SEC-022)."
    )


# --------------------------------------------------------------------------
# Live probes (excluded from CI via -m "not live")
# --------------------------------------------------------------------------


@pytest.mark.live
async def test_live_status_counts_cubes():
    status = await server.api_status()
    assert status.reachable is True
    assert status.cube_count and status.cube_count > 1000


@pytest.mark.live
async def test_live_search_and_structure_roundtrip():
    hits = await server.search_cubes(query="wald", language="de", limit=3)
    assert hits.returned > 0
    structure = await server.get_cube_structure(cube_uri=hits.cubes[0].cube_uri)
    assert structure.dimensions


@pytest.mark.live
async def test_live_municipality_resolves_zurich():
    result = await server.resolve_municipality(name_or_bfs="261")
    assert any(m.name and "rich" in m.name for m in result.municipalities)


@pytest.mark.live
async def test_live_observations_resolve_labels():
    """The observationSet indirection (fundstück 6) — only a live test proves it."""
    hits = await server.search_cubes(query="waldbrand", language="de", limit=5)
    assert hits.returned > 0
    obs = await server.query_cube_observations(
        cube_uri=hits.cubes[0].cube_uri, limit=3, resolve_labels=True
    )
    assert obs.returned > 0


@pytest.mark.live
async def test_live_vollstaendigkeitsangabe_in_beiden_richtungen():
    """Both branches of `truncated` against the real store, self-calibrating.

    Recorded 2026-09-20: «wald» matches 127 published cube versions, which
    collapse to 35 logical cubes. Those numbers are today's and will drift, so
    the test reads the total from the store and derives its own limits from it
    instead of pinning them. A hard-coded 127 would go red on the day BAFU
    publishes a new version — a test that measures the day rather than the
    mechanism.

    The third assertion is the drift watch under the design: it holds that
    collapsing versions really does shrink the number. If that spread ever
    vanished, `total_matched is None` for `latest_only=True` would have lost its
    justification and this test says so.
    """
    async with c.build_client() as http:
        gemeinsam = dict(query="wald", language="de", creator_uri=None)

        # Branch 1: capped, latest_only=False -> the count query has to answer.
        knapp = await cube.search(http, **gemeinsam, limit=5, latest_only=False)
        total = knapp["total_matched"]
        assert knapp["truncated"] is True
        assert isinstance(total, int) and total >= 5, knapp
        assert len(knapp["cubes"]) == 5

        # Branch 2: ask past the end -> nothing is capped, so the total is exact
        # and truncated must be False. The limit comes from branch 1, not from a
        # literal. If this goes red, the store now carries far more unpublished
        # than published rows for the term and the margin needs revisiting.
        weit = await cube.search(http, **gemeinsam, limit=total + 20, latest_only=False)
        assert weit["truncated"] is False, weit["total_matched"]
        assert weit["total_matched"] == len(weit["cubes"]) == total

        # Branch 3: capped AND latest_only -> unknown, and it says so.
        gedeckelt = await cube.search(http, **gemeinsam, limit=3, latest_only=True)
        assert gedeckelt["truncated"] is True
        assert gedeckelt["total_matched"] is None, gedeckelt["total_matched"]

        # The premise itself: versions outnumber the cubes they collapse to.
        neueste = await cube.search(http, **gemeinsam, limit=total + 20, latest_only=True)
        assert neueste["total_matched"] is not None
        assert neueste["total_matched"] < total, (
            f"Versionen ({total}) und kollabierte Cubes ({neueste['total_matched']}) "
            "fallen nicht mehr auseinander — dann braucht das None bei latest_only "
            "eine neue Begruendung"
        )
