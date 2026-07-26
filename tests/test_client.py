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

    monkeypatch.setattr(c.asyncio, "sleep", _instant)


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
async def test_timeout_raises_upstream_with_anchor_hint():
    respx.get(EP).mock(side_effect=httpx.ConnectTimeout("timed out"))
    async with c.build_client() as http:
        with pytest.raises(c.UpstreamError) as exc:
            await c.run_query(http, "SELECT ?s WHERE {}")
    # The error must teach the caller how to avoid the timeout next time.
    assert "anchor" in str(exc.value).lower()


@respx.mock
async def test_long_query_uses_post():
    get_route = respx.get(EP).mock(return_value=httpx.Response(200, json=_results()))
    post_route = respx.post(EP).mock(return_value=httpx.Response(200, json=_results()))
    long_query = "SELECT ?s WHERE {}" + " " * (c.GET_QUERY_LIMIT + 10)
    async with c.build_client() as http:
        await c.run_query(http, long_query)
    assert post_route.called
    assert not get_route.called
