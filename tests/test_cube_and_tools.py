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
from lindas_mcp.lindas import cube

EP = c.ENDPOINT


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _instant(_seconds):
        return None

    monkeypatch.setattr(c.asyncio, "sleep", _instant)


def _results(*rows: dict) -> dict:
    bindings = [{k: {"value": v} for k, v in row.items()} for row in rows]
    return {"head": {"vars": []}, "results": {"bindings": bindings}}


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
    assert len(result) == 1
    assert result[0]["version"] == "2024.1"


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
    assert len(result) == 2


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
