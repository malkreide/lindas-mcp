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
import functools
import hashlib
import json as _json
import os
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, TypeVar

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from .lindas import cube
from .lindas.client import (
    ENDPOINT,
    SparqlError,
    UpstreamError,
    build_client,
    client_session,
    last_success,
    run_query,
    set_shared_client,
)
from .logging_config import configure_logging, logger
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


@asynccontextmanager
async def _lifespan(_server: MCPServer) -> AsyncIterator[None]:
    """SDK-001: build one pooled httpx client for the process lifetime and share
    it across all tool calls, instead of opening a fresh client per call."""
    async with build_client() as http:
        set_shared_client(http)
        logger.info("lindas_mcp.startup", endpoint=ENDPOINT)
        try:
            yield
        finally:
            set_shared_client(None)
            logger.info("lindas_mcp.shutdown")


mcp = MCPServer("lindas-mcp", lifespan=_lifespan)

Language = Literal["de", "fr", "it", "rm", "en"]

# ARCH-009: read-only tools that reach an external endpoint and are idempotent.
READ_ONLY: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

RUN_SPARQL_TIMEOUT = 30.0
RUN_SPARQL_ROW_CAP = 500

# SEC-018: schema-level bounds on tool inputs (rejected as a ValidationError at
# the boundary, not silently clamped). `Language` above is already a Literal.
SearchLimit = Annotated[int, Field(ge=1, le=100)]
ObsLimit = Annotated[int, Field(ge=1, le=500)]
Topic = Annotated[str, Field(min_length=1, max_length=200)]
CubeUri = Annotated[str, Field(min_length=1, max_length=500)]
MuniQuery = Annotated[str, Field(min_length=1, max_length=200)]
SparqlQuery = Annotated[str, Field(min_length=1, max_length=8000)]

_T = TypeVar("_T")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def mask_errors(fn: Callable[..., Awaitable[_T]]) -> Callable[..., Awaitable[_T]]:
    """OBS-002: log full detail server-side, but never surface an unexpected
    exception's raw message to the LLM.

    Known, LLM-safe errors (`SparqlError`, `UpstreamError` — they carry only the
    public endpoint's own diagnostics) propagate unchanged. Anything else is
    logged with its type/message to stderr and re-raised as a generic error so
    internal detail cannot leak through the tool result.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> _T:
        try:
            return await fn(*args, **kwargs)
        except (SparqlError, UpstreamError):
            raise
        except Exception as exc:  # noqa: BLE001 — deliberate catch-log-mask
            logger.error(
                "lindas_mcp.tool_error",
                tool=fn.__name__,
                error_type=type(exc).__name__,
                error=str(exc)[:500],
            )
            raise RuntimeError(
                f"{fn.__name__} failed with an internal error; see server logs."
            ) from None

    return wrapper


async def _log_call(ctx: Context | None, tool: str, started: float, **fields: Any) -> None:
    """Emit a structured per-call log line (OBS-003) and an MCP debug event."""
    ms = round((time.monotonic() - started) * 1000)
    logger.info("lindas_mcp.tool_call", tool=tool, ms=ms, **fields)
    if ctx is not None:
        await ctx.debug(f"{tool} done in {ms} ms")


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
@mask_errors
async def search_cubes(
    query: Topic,
    language: Language = "de",
    creator_uri: str | None = None,
    limit: SearchLimit = 20,
    latest_only: bool = True,
    ctx: Context | None = None,
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
    started = time.monotonic()
    async with client_session() as http:
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
    await _log_call(ctx, "search_cubes", started, returned=len(hits))
    return CubeSearchResult(
        retrieved_at=_now(),
        query=query or None,
        language=language,
        latest_only=latest_only,
        returned=len(hits),
        match_type="exact" if hits else "none",
        suggestion=(
            None
            if hits
            else (
                "No cubes matched. Try a broader term or the German label, widen "
                "with latest_only=False, or use list_publishers to browse by authority."
            )
        ),
        cubes=hits,
    )


@mcp.tool(annotations=READ_ONLY)
@mask_errors
async def get_cube_structure(
    cube_uri: CubeUri,
    language: Language = "de",
    ctx: Context | None = None,
) -> CubeStructureResult:
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
    started = time.monotonic()
    async with client_session() as http:
        s = await cube.get_structure(http, cube_uri=cube_uri, language=language)
    await _log_call(ctx, "get_cube_structure", started)
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
@mask_errors
async def query_cube_observations(
    cube_uri: CubeUri,
    language: Language = "de",
    limit: ObsLimit = 50,
    resolve_labels: bool = True,
    ctx: Context | None = None,
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
    started = time.monotonic()
    if ctx is not None:
        await ctx.report_progress(0, 2)
    async with client_session() as http:
        data = await cube.get_observations(
            http,
            cube_uri=cube_uri,
            language=language,
            limit=limit,
            resolve_labels=resolve_labels,
        )
    if ctx is not None:
        await ctx.report_progress(2, 2)
    await _log_call(ctx, "query_cube_observations", started, returned=data.get("returned"))
    return ObservationsResult(retrieved_at=_now(), **data)


# --------------------------------------------------------------------------
# Actors and geography
# --------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
@mask_errors
async def list_publishers(ctx: Context | None = None) -> PublisherListResult:
    """List the federal bodies that publish cubes, with cube counts.

    Returns creator URIs you can pass to `search_cubes` to restrict a search
    to one authority.
    """
    started = time.monotonic()
    async with client_session() as http:
        pubs = await cube.list_publishers(http)
    await _log_call(ctx, "list_publishers", started, returned=len(pubs))
    return PublisherListResult(
        retrieved_at=_now(),
        returned=len(pubs),
        publishers=[Publisher(**p) for p in pubs],
    )


@mcp.tool(annotations=READ_ONLY)
@mask_errors
async def resolve_municipality(
    name_or_bfs: MuniQuery,
    language: Language = "de",
    ctx: Context | None = None,
) -> MunicipalityResult:
    """Resolve a Swiss municipality to its LINDAS URI and BFS number.

    The BFS commune number is the join key across the whole portfolio: the
    same number identifies the municipality in swiss-statistics-mcp,
    zurich-opendata-mcp and any cube that references a place. In LINDAS the
    URI is literally ld.admin.ch/municipality/<BFS>.

    Args:
        name_or_bfs: A municipality name ("Zürich") or a BFS number ("261").
        language: Language for the name.
    """
    started = time.monotonic()
    async with client_session() as http:
        munis = await cube.resolve_municipality(http, name_or_bfs=name_or_bfs, language=language)
    await _log_call(ctx, "resolve_municipality", started, returned=len(munis))
    return MunicipalityResult(
        retrieved_at=_now(),
        query=name_or_bfs,
        returned=len(munis),
        match_type="exact" if munis else "none",
        suggestion=(
            None
            if munis
            else (
                "No municipality matched. Check spelling (try the official name), "
                "or pass the BFS commune number directly."
            )
        ),
        municipalities=[Municipality(**m) for m in munis],
    )


# --------------------------------------------------------------------------
# Escape hatch and operations
# --------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
@mask_errors
async def run_sparql(query: SparqlQuery, ctx: Context | None = None) -> SparqlResult:
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
    started = time.monotonic()
    async with client_session() as http:
        rows = await run_query(http, query, timeout_s=RUN_SPARQL_TIMEOUT)
    await _log_call(ctx, "run_sparql", started, rows=len(rows))
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
async def api_status(ctx: Context | None = None) -> StatusResult:
    """Check whether the LINDAS SPARQL endpoint is reachable.

    Returns an evaluable status even on failure, so an agent can tell "no data
    matched" apart from "the endpoint is down".
    """
    count_query = (
        "PREFIX cube: <https://cube.link/> "
        "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c a cube:Cube }"
    )
    try:
        async with client_session() as http:
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
    entries = [{"name": tool.name, **_stable_signature(tool.input_schema or {})} for tool in tools]
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


def build_transport_security(host: str, port: int):
    """Host/Origin allow-list for the HTTP/SSE transports (SEC-005, inbound).

    The SDK leaves DNS-rebinding protection OFF while ``transport_security`` is
    unset — its own source says "If not specified, disable DNS rebinding
    protection by default for backwards compatibility". Unset therefore means
    no Host and no Origin validation at all.

    Returns ``None`` when no allow-list can be derived: a non-loopback bind
    with no ``LINDAS_MCP_ALLOWED_HOSTS``. The server is then reached under a
    service or public DNS name this process does not know, and a guessed list
    would reject every real request with HTTP 421. The caller warns instead.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    allowed = [h.strip() for h in os.getenv("LINDAS_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    loopback = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    if allowed:
        # Loopback stays reachable for container health checks and debugging.
        hosts = set(allowed) | loopback
    elif host in ("127.0.0.1", "localhost", "::1"):
        hosts = loopback | {f"{host}:{port}"}
    else:
        return None

    # Configured CORS origins must also pass the transport check, or the server
    # rejects exactly the browser clients CORS permits. "*" cannot be expressed
    # here (origins are matched literally, only a trailing ":*" port wildcard
    # exists), so it is not copied across.
    raw_origins = os.getenv("ALLOWED_ORIGINS", "")
    configured = [o.strip() for o in raw_origins.split(",") if o.strip()]
    origins = {o for o in configured if o != "*"}
    origins |= {f"http://{h}" for h in hosts}
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(hosts),
        allowed_origins=sorted(origins),
    )


def build_http_app(transport: str) -> Any:
    """Build the SSE / streamable-http ASGI app with CORS configured.

    MCPServer.run() serves the ASGI app without CORS, so browser clients cannot
    read the `Mcp-Session-Id` response header and lose their session (SDK-004).
    We build the app ourselves and expose that header via CORS.
    """
    from starlette.middleware.cors import CORSMiddleware

    # SDK-004: origins are configurable via ALLOWED_ORIGINS (comma-separated).
    # Default `*` keeps local/dev usage frictionless; set an explicit list in
    # production so only known browser origins can reach a hosted server.
    raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
    origins = ["*"] if raw == "*" else [o.strip() for o in raw.split(",") if o.strip()]

    app = mcp.sse_app() if transport == "sse" else mcp.streamable_http_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
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

    security = build_transport_security(host, port)
    if security is None:
        logger.warning(
            "dns_rebinding_protection_off",
            host=host,
            hint="Set LINDAS_MCP_ALLOWED_HOSTS to the hostnames this server is "
            "reachable under; without it the Host header is not checked at all.",
        )
    mcp.settings.transport_security = security
    uvicorn.run(build_http_app(transport), host=host, port=port, log_level="info")


def main() -> None:
    """Entry point. Transport via LINDAS_MCP_TRANSPORT (stdio | sse | http)."""
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
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
