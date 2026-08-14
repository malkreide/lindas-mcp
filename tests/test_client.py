"""Layer-1 client tests: retry, malformed-query passthrough, timeout, POST."""

from __future__ import annotations

import httpx
import pytest
import respx

from lindas_mcp.lindas import client as c

EP = c.ENDPOINT


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _instant(_seconds):
        return None

    monkeypatch.setattr(c, "_sleep", _instant)


def _results(*rows: dict) -> dict:
    """Build a minimal SPARQL JSON results envelope."""
    bindings = [{k: {"value": v} for k, v in row.items()} for row in rows]
    return {"head": {"vars": []}, "results": {"bindings": bindings}}


@respx.mock
async def test_parses_bindings_to_flat_rows():
    respx.get(EP).mock(return_value=httpx.Response(200, json=_results({"cube": "u1", "name": "A"})))
    async with c.build_client() as http:
        rows = await c.run_query(http, "SELECT ?cube ?name WHERE {}")
    assert rows == [{"cube": "u1", "name": "A"}]


@respx.mock
async def test_malformed_query_raises_sparql_error_with_diagnostic():
    respx.get(EP).mock(return_value=httpx.Response(400, text="MALFORMED QUERY: Encountered <EOF>"))
    async with c.build_client() as http:
        with pytest.raises(c.SparqlError) as exc:
            await c.run_query(http, "SELECT ?s WHERE { ?s ?p")
    assert "MALFORMED" in str(exc.value)


@respx.mock
async def test_400_is_not_retried():
    route = respx.get(EP).mock(return_value=httpx.Response(400, text="bad"))
    async with c.build_client() as http:
        with pytest.raises(c.SparqlError):
            await c.run_query(http, "SELECT ?s WHERE {}")
    assert route.call_count == 1


@respx.mock
async def test_retries_on_503_then_succeeds():
    route = respx.get(EP).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=_results())]
    )
    async with c.build_client() as http:
        rows = await c.run_query(http, "SELECT ?s WHERE {}")
    assert route.call_count == 2
    assert rows == []


@respx.mock
async def test_read_timeout_raises_upstream_with_anchor_hint():
    # A read timeout means the store accepted the query and took too long —
    # the one case where "your query was too broad" is a diagnosis and not a
    # guess. Only here may the hint appear.
    respx.get(EP).mock(side_effect=httpx.ReadTimeout("timed out"))
    async with c.build_client() as http:
        with pytest.raises(c.UpstreamError) as exc:
            await c.run_query(http, "SELECT ?s WHERE {}")
    assert "anchor" in str(exc.value).lower()


@respx.mock
async def test_connect_error_names_the_type_and_withholds_the_hint():
    """OBS-007: an empty ``str(exc)`` must not leave the message saying nothing.

    This asserted the opposite until 2026-08-02: a ``ConnectTimeout`` — which
    never reached the store — was expected to carry the "query was too broad"
    hint. httpx timeout and connect errors also carry an *empty* ``str()``, so
    the message read "Last error: ." followed by a confident misdiagnosis.
    An empty message says nothing; an empty message with a guess attached says
    something false.
    """
    respx.get(EP).mock(side_effect=httpx.ConnectError(""))  # leere Message: der reale Fall
    async with c.build_client() as http:
        with pytest.raises(c.UpstreamError) as exc:
            await c.run_query(http, "SELECT ?s WHERE {}")
    msg = str(exc.value)
    assert "ConnectError" in msg  # Typ überlebt die leere Message
    assert "lindas.admin.ch" in msg  # Ziel benannt
    assert "anchor" not in msg.lower()  # keine Ursachenbehauptung ohne Grundlage
    assert isinstance(exc.value.__cause__, httpx.ConnectError)


@respx.mock
async def test_long_query_uses_post():
    get_route = respx.get(EP).mock(return_value=httpx.Response(200, json=_results()))
    post_route = respx.post(EP).mock(return_value=httpx.Response(200, json=_results()))
    long_query = "SELECT ?s WHERE {}" + " " * (c.GET_QUERY_LIMIT + 10)
    async with c.build_client() as http:
        await c.run_query(http, long_query)
    assert post_route.called
    assert not get_route.called


def test_endpoint_host_is_on_the_egress_allow_list():
    """SEC-021: the only host the client ever targets must be allow-listed."""
    c.assert_host_allowed(c.ENDPOINT)


def test_assert_host_allowed_rejects_off_host_url():
    """SEC-021: an off-host URL is refused before any client is built."""
    with pytest.raises(c.UpstreamError) as exc:
        c.assert_host_allowed("https://evil.example.com/query")
    assert "not allowed" in str(exc.value)
