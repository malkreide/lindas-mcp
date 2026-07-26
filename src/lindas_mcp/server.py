"""MCP server for LINDAS — the Linked Data Service of the Swiss administration.

LINDAS is a SPARQL knowledge graph run by the Federal Archives. It holds ~2000
statistical data cubes (cube.link) from federal offices, plus the geo-linked
data that underpins visualize.admin.ch. This server exposes it through guarded
tools rather than raw SPARQL, because the store rewards precise queries and
times out on broad ones.

The design enforces two-phase access: read a cube's structure, then read its
data with codes already resolved to labels.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json as _json
import os
import sys
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .lindas import cube
from .lindas.client import (
    ENDPOINT,
    SparqlError,
    UpstreamError,
    build_client,
    last_success,
    run_query,
)
from .models import (
    CubeHit,
    CubeSearchResult,
    CubeStructureResult,
    Dimension,
    Municipality,
    MunicipalityResult,
    ObservationsResult,
    Publisher,
    PublisherListResult,
    SparqlResult,
    StatusResult,
)

mcp = FastMCP("lindas-mcp")

Language = Literal["de", "fr", "it", "rm", "en"]
READ_ONLY: dict[str, Any] = {"readOnlyHint": True, "destructiveHint": False}

RUN_SPARQL_TIMEOUT = 30.0
RUN_SPARQL_ROW_CAP = 500


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def search_cubes(
    query: str,
    language: Language = "de",
    creator_uri: str | None = None,
    limit: int = 20,
    latest_only: bool = True,
) -> CubeSearchResult:
    """Find statistical data cubes in LINDAS by topic.

    The entry point. Returns cube URIs you then pass to `get_cube_structure`.
    By default only the newest published version of each cube is returned;
    set `latest_only=False` to see every version.

    Args:
        query: Topic term, e.g. "Wald", "Abfluss", "Energie". Matched against
            cube names and descriptions in the chosen language.
        language: Language for names and descriptions.
        creator_uri: Restrict to one publishing body (from `list_publishers`).
        limit: Maximum cubes to return (1-100).
        latest_only: Collapse versions to the newest per cube.
    """
    limit = _clamp(limit, 1, 100)
    async with build_client() as http:
        rows = await cube.search(
            http,
            query=query,
            language=language,
            creator_uri=creator_uri,
            limit=limit,
            latest_only=latest_only,
        )
    hits = [
        CubeHit(
            cube_uri=r["cube"],
            name=r.get("name"),
            description=r.get("desc"),
            creator=r.get("creator"),
            version=r.get("version"),
            status=(r.get("status") or "").rsplit("/", 1)[-1] or None,
        )
        for r in rows
    ]
    return CubeSearchResult(
        retrieved_at=_now(),
        query=query or None,
        language=language,
        latest_only=latest_only,
        returned=len(hits),
        cubes=hits,
    )


@mcp.tool(annotations=READ_ONLY)
async def get_cube_structure(cube_uri: str, language: Language = "de") -> CubeStructureResult:
    """Read a cube's dimensions and measures — always call this before data.

    This is phase 1 of the two-phase access pattern. It tells you which
    dimensions you can filter on (`KeyDimension`), which values are measured
    (`MeasureDimension`), and which dimensions carry code lists. It also
    returns the licence, which is frequently a Fedlex URI you can resolve with
    fedlex-mcp.

    Args:
        cube_uri: A cube URI from `search_cubes`.
        language: Language for dimension names and description.
    """
    async with build_client() as http:
        s = await cube.get_structure(http, cube_uri=cube_uri, language=language)
    return CubeStructureResult(
        retrieved_at=_now(),
        cube_uri=s["cube_uri"],
        name=s["name"],
        description=s["description"],
        creator_name=s["creator_name"],
        version=s["version"],
        status=s["status"],
        licence=s["licence"],
        dimensions=[Dimension(**d) for d in s["dimensions"]],
    )


@mcp.tool(annotations=READ_ONLY)
async def query_cube_observations(
    cube_uri: str,
    language: Language = "de",
    limit: int = 50,
    resolve_labels: bool = True,
) -> ObservationsResult:
    """Read the actual data points of a cube, with codes resolved to labels.

    This is phase 2. Values are returned keyed by human-readable dimension
    names, and coded dimension values (e.g. region "1805") are replaced by
    their labels (e.g. "Alpennordhang") unless you turn that off.

    For large cubes this reads only the first `limit` observations. LINDAS has
    no cheap way to filter observations server-side by arbitrary dimension
    value, so heavy analytical slicing belongs in `run_sparql`.

    Args:
        cube_uri: A cube URI from `search_cubes`.
        language: Language for labels.
        limit: Maximum observations to return (1-500).
        resolve_labels: Replace coded values with human labels.
    """
    limit = _clamp(limit, 1, 500)
    async with build_client() as http:
        data = await cube.get_observations(
            http,
            cube_uri=cube_uri,
            language=language,
            limit=limit,
            resolve_labels=resolve_labels,
        )
    return ObservationsResult(retrieved_at=_now(), **data)


# --------------------------------------------------------------------------
# Actors and geography
# --------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def list_publishers() -> PublisherListResult:
    """List the federal bodies that publish cubes, with cube counts.

    Returns creator URIs you can pass to `search_cubes` to restrict a search
    to one authority.
    """
    async with build_client() as http:
        pubs = await cube.list_publishers(http)
    return PublisherListResult(
        retrieved_at=_now(),
        returned=len(pubs),
        publishers=[Publisher(**p) for p in pubs],
    )


@mcp.tool(annotations=READ_ONLY)
async def resolve_municipality(name_or_bfs: str, language: Language = "de") -> MunicipalityResult:
    """Resolve a Swiss municipality to its LINDAS URI and BFS number.

    The BFS commune number is the join key across the whole portfolio: the
    same number identifies the municipality in swiss-statistics-mcp,
    zurich-opendata-mcp and any cube that references a place. In LINDAS the
    URI is literally ld.admin.ch/municipality/<BFS>.

    Args:
        name_or_bfs: A municipality name ("Zürich") or a BFS number ("261").
        language: Language for the name.
    """
    async with build_client() as http:
        munis = await cube.resolve_municipality(http, name_or_bfs=name_or_bfs, language=language)
    return MunicipalityResult(
        retrieved_at=_now(),
        query=name_or_bfs,
        returned=len(munis),
        municipalities=[Municipality(**m) for m in munis],
    )


# --------------------------------------------------------------------------
# Escape hatch and operations
# --------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def run_sparql(query: str) -> SparqlResult:
    """Run a raw SPARQL SELECT query. Advanced escape hatch — use sparingly.

    Prefer the structured tools. This exists for analytical queries the guarded
    tools cannot express (cross-cube joins, aggregations, custom filters).

    Guardrails, learned from probing: LINDAS times out on unanchored scans, so
    always anchor on a known class such as `?x a <https://cube.link/Cube>`.
    A bare `SELECT * WHERE { ?s ?p ?o }` will time out. This tool caps the
    result at 500 rows and the runtime at 30 seconds.

    Args:
        query: A complete SPARQL SELECT query, including its own PREFIX lines.
    """
    async with build_client() as http:
        rows = await run_query(http, query, timeout_s=RUN_SPARQL_TIMEOUT)
    capped = rows[:RUN_SPARQL_ROW_CAP]
    return SparqlResult(
        retrieved_at=_now(),
        row_count=len(capped),
        rows=capped,
        note=(
            f"Returned {len(capped)} of {len(rows)} rows (cap {RUN_SPARQL_ROW_CAP}). "
            "Anchor queries on a known class to avoid timeouts."
            if len(rows) > RUN_SPARQL_ROW_CAP
            else "Anchor queries on a known class to avoid timeouts."
        ),
    )


@mcp.tool(annotations=READ_ONLY)
async def api_status() -> StatusResult:
    """Check whether the LINDAS SPARQL endpoint is reachable.

    Returns an evaluable status even on failure, so an agent can tell "no data
    matched" apart from "the endpoint is down".
    """
    count_query = (
        "PREFIX cube: <https://cube.link/> "
        "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a cube:Cube }"
    )
    try:
        async with build_client() as http:
            rows = await run_query(http, count_query, timeout_s=20.0)
        n = int(rows[0]["n"]) if rows else None
        return StatusResult(
            retrieved_at=_now(),
            reachable=True,
            endpoint=ENDPOINT,
            cube_count=n,
            last_successful_call=last_success(),
            note="LINDAS reachable. Read access needs no authentication.",
        )
    except (UpstreamError, SparqlError) as exc:
        return StatusResult(
            retrieved_at=_now(),
            reachable=False,
            endpoint=ENDPOINT,
            last_successful_call=last_success(),
            note=f"LINDAS unreachable: {str(exc)[:200]}",
        )


# --------------------------------------------------------------------------
# Tool-definition integrity (SEC-022)
# --------------------------------------------------------------------------


def _stable_signature(schema: dict[str, Any]) -> dict[str, Any]:
    """Project a tool's input schema to its rug-pull-relevant surface.

    Deliberately captures only the *contract* — the argument names and which are
    required — not the pydantic/mcp-version-specific serialisation of constraints
    (minimum/maximum/pattern/title/anyOf), so the lock is stable across SDK patch
    upgrades. Argument-level constraints live in the reviewed source and CHANGELOG.
    """
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    return {
        "arguments": sorted(props),
        "required": sorted(schema.get("required", []) if isinstance(schema, dict) else []),
    }


async def tool_manifest() -> dict[str, Any]:
    """Return a deterministic hash snapshot of the registered tool definitions.

    Committed as `tool-definitions.lock.json` and checked in CI so a silent
    change to the tool set, a tool's name, or its argument surface (a rug-pull)
    fails the build until the lock is regenerated and reviewed. The snapshot
    covers only what is derived from the source function signatures — tool name,
    argument names, and which are required — because that is stable across
    mcp/pydantic patch upgrades. Docstrings are governed by PR review + CHANGELOG.
    """
    tools = sorted(await mcp.list_tools(), key=lambda t: t.name)
    entries = [
        {"name": tool.name, **_stable_signature(tool.inputSchema or {})} for tool in tools
    ]
    combined = hashlib.sha256(
        _json.dumps(entries, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "server": "lindas-mcp",
        "tool_count": len(entries),
        "combined_sha256": combined,
        "tools": entries,
    }


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


def build_http_app(transport: str) -> Any:
    """Build the SSE / streamable-http ASGI app with CORS configured.

    FastMCP.run() serves the ASGI app without CORS, so browser clients cannot
    read the `Mcp-Session-Id` response header and lose their session (SDK-004).
    We build the app ourselves and expose that header via CORS.
    """
    from starlette.middleware.cors import CORSMiddleware

    app = mcp.sse_app() if transport == "sse" else mcp.streamable_http_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*", "Mcp-Session-Id"],
        # Browsers only read a response header if it is listed here, and MCP
        # clients need Mcp-Session-Id to keep a session.
        expose_headers=["Mcp-Session-Id"],
    )
    return app


def _run_http(transport: str, host: str, port: int) -> None:
    """Serve the CORS-wrapped SSE / streamable-http app with uvicorn."""
    import uvicorn

    uvicorn.run(build_http_app(transport), host=host, port=port, log_level="info")


def main() -> None:
    """Entry point. Transport via LINDAS_MCP_TRANSPORT (stdio | sse | http)."""
    transport = os.getenv("LINDAS_MCP_TRANSPORT", "stdio").lower()
    if transport in {"sse", "streamable-http", "http"}:
        # SEC-016: default to loopback. Binding to all interfaces is an
        # explicit opt-in (the container image sets HOST=0.0.0.0 on purpose).
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        if host == "0.0.0.0":  # noqa: S104 — intentional, warned about below
            print(
                "lindas-mcp: binding to 0.0.0.0 exposes the server on all network "
                "interfaces; run it only behind a reverse proxy / firewall.",
                file=sys.stderr,
            )
        mcp.settings.host = host
        mcp.settings.port = port
        _run_http("sse" if transport == "sse" else "streamable-http", host, port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
