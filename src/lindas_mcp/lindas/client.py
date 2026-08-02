"""Layer 1 — the raw SPARQL/HTTP client.

This module knows only two things: how to send a SPARQL query over HTTP, and
how to turn the JSON result bindings into flat dicts. It knows nothing about
data cubes. That separation is deliberate: this file is the part that ports
unchanged to any other LINDAS-backed server.

Resilience defaults follow the Swiss Public Data MCP Portfolio standard.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx

ENDPOINT = "https://lindas.admin.ch/query"

# SEC-021: code-layer egress allow-list. A `frozenset` (not env-configurable) is
# the single destination this server may ever reach. `assert_host_allowed` runs
# before the client is built, and `follow_redirects=False` refuses any off-host
# redirect. The network-layer counterpart is documented in
# `docs/network-egress.md`.
ALLOWED_HOSTS: frozenset[str] = frozenset({"lindas.admin.ch"})

ATTRIBUTION = (
    "Data: LINDAS Linked Data Service, Swiss Federal Archives — "
    "https://lindas.admin.ch. Each cube declares its own licence; check the "
    "`licence` field before reuse."
)

USER_AGENT = "lindas-mcp (+https://github.com/malkreide/lindas-mcp)"

# The LINDAS store aborts expensive queries itself at 60-90s and then returns
# an empty/closed connection (observed as HTTP 000 during probing). We cut in
# front of that with a client-side timeout so the agent gets a clean error
# rather than a silent hang.
TIMEOUT_S = 45.0
MAX_ATTEMPTS = 4

# Queries longer than this are sent via POST to avoid URL-length limits.
GET_QUERY_LIMIT = 1500


class SparqlError(RuntimeError):
    """The endpoint rejected the query (HTTP 400, malformed SPARQL)."""


class UpstreamError(RuntimeError):
    """The endpoint was unreachable or timed out after all retries."""


_LAST_SUCCESS: dict[str, str] = {}


def last_success() -> str | None:
    return _LAST_SUCCESS.get("ts")


def _record_success() -> None:
    _LAST_SUCCESS["ts"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def assert_host_allowed(url: str) -> None:
    """Raise UpstreamError if `url`'s host is not on the egress allow-list."""
    host = urlsplit(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise UpstreamError(
            f"Egress to {host!r} is not allowed (allow-list: {sorted(ALLOWED_HOSTS)})."
        )


def build_client() -> httpx.AsyncClient:
    """Create a configured AsyncClient. Caller owns the lifecycle."""
    assert_host_allowed(ENDPOINT)
    return httpx.AsyncClient(
        timeout=TIMEOUT_S,
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": USER_AGENT,
        },
        # A SPARQL query endpoint answers directly (HTTP 200); an off-host
        # redirect is surfaced as an error rather than followed (SEC-021).
        follow_redirects=False,
    )


# SDK-001: a single client is installed by the server lifespan and reused across
# tool calls (connection pooling). When no lifespan is running — e.g. in direct
# unit tests — `client_session()` falls back to a fresh per-call client.
_SHARED: dict[str, httpx.AsyncClient] = {}


def set_shared_client(client: httpx.AsyncClient | None) -> None:
    """Install (or clear) the process-wide pooled client. Called by the lifespan."""
    if client is None:
        _SHARED.pop("client", None)
    else:
        _SHARED["client"] = client


def get_shared_client() -> httpx.AsyncClient | None:
    """Return the lifespan-installed pooled client, if any."""
    return _SHARED.get("client")


@asynccontextmanager
async def client_session() -> AsyncIterator[httpx.AsyncClient]:
    """Yield the shared pooled client if the lifespan installed one, otherwise a
    fresh short-lived client that is closed on exit.

    This lets tools run both under the server lifespan (pooled, long-lived
    client) and in direct unit tests that call them without a running lifespan.
    """
    shared = get_shared_client()
    if shared is not None:
        yield shared
    else:
        async with build_client() as http:
            yield http


async def run_query(
    http: httpx.AsyncClient,
    query: str,
    *,
    timeout_s: float | None = None,
) -> list[dict[str, Any]]:
    """Execute a SPARQL SELECT/ASK query and return flat result rows.

    Retries transient failures (5xx, 429, network) with 2s/4s/8s backoff.
    A 400 is a query error — it is raised immediately, never retried, and
    carries the endpoint's own diagnostic so the caller can see what was
    malformed.
    """
    use_post = len(query) > GET_QUERY_LIMIT
    last_error: Exception | None = None
    effective_timeout = timeout_s or TIMEOUT_S

    for attempt in range(MAX_ATTEMPTS):
        if attempt > 0:
            await asyncio.sleep(2**attempt)
        try:
            if use_post:
                resp = await http.post(
                    ENDPOINT,
                    content=query.encode("utf-8"),
                    headers={"Content-Type": "application/sparql-query"},
                    timeout=effective_timeout,
                )
            else:
                resp = await http.get(ENDPOINT, params={"query": query}, timeout=effective_timeout)

            if resp.status_code == 400:
                raise SparqlError(f"LINDAS rejected the query: {resp.text.strip()[:400]}")
            resp.raise_for_status()
            _record_success()
            return _parse_bindings(resp.json())

        except SparqlError:
            raise
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            if 400 <= status < 500 and status != 429:
                raise UpstreamError(f"LINDAS returned {status}: {exc.response.text[:200]}") from exc
        except httpx.RequestError as exc:
            last_error = exc

    # OBS-007: httpx timeout/connect errors carry an empty str(), so the type
    # has to be named explicitly — otherwise this message read "Last error: ."
    detail = str(last_error) or "no further detail"
    # The anchor hint fits exactly one failure: the store accepted the query and
    # took too long to answer. A ConnectError never reached it, so blaming the
    # query there would be a guess dressed as a diagnosis — and it was, until
    # this line became conditional.
    hint = (
        " The store timed out while answering, which often means the query was "
        "too broad — anchor it on a known class such as `?x a cube:Cube`."
        if isinstance(last_error, httpx.ReadTimeout)
        else ""
    )
    raise UpstreamError(
        f"LINDAS unreachable after {MAX_ATTEMPTS} attempts "
        f"(host={urlsplit(ENDPOINT).hostname}): "
        f"{type(last_error).__name__}: {detail}.{hint} "
        f"Last success: {last_success() or 'none this session'}."
    ) from last_error


def _parse_bindings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten SPARQL JSON results to a list of {var: value} dicts.

    Keeps only the literal/URI value string; datatype and language are dropped
    because the cube layer handles language selection explicitly.
    """
    rows: list[dict[str, Any]] = []
    for binding in payload.get("results", {}).get("bindings", []):
        row = {var: cell.get("value") for var, cell in binding.items()}
        rows.append(row)
    return rows
