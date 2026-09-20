"""Layer 2 — the cube.link vocabulary guardrail.

This layer knows the cube.link model and enforces the two-phase access pattern:
read the structure before reading the data, and resolve codes to labels before
the caller ever sees them. The tools in server.py talk to this layer, never to
the raw client — that is what keeps the raw SPARQL sealed away from the agent.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from . import queries
from .client import SparqlError, UpstreamError, run_query

# Cube URIs end in a version segment: .../cube/2024-1 or a trailing /1. We strip
# it to group versions of the same logical cube for deduplication.
_VERSION_SUFFIX = re.compile(r"/(cube/)?\d{4}-\d+$|/\d+$")

# Budget for the completeness count in `search`, well under the 45s a search
# itself gets. The count is a nicety and the hits are the deliverable, so it
# must never be the reason a search comes back empty-handed.
#
# Measured against the live store on 2026-09-20, `queries.count_cubes` over
# «wald», «energie», «e» and a term that matches nothing: 230-932 ms. The 8s
# here is roughly nine times the slowest of those, and the two slowest readings
# were each the first request of a run, i.e. TLS setup rather than the query.
COUNT_BUDGET_S = 8.0


def _base_cube_uri(cube_uri: str) -> str:
    return _VERSION_SUFFIX.sub("", cube_uri)


def _local_name(uri: str) -> str:
    return uri.rstrip("/").split("/")[-1] if uri else uri


async def _count_matches(
    http: httpx.AsyncClient, *, query: str, language: str, creator_uri: str | None
) -> int | None:
    """Total number of matching cubes, or None if the store would not say.

    A failure here is not a failed search: the caller already holds the hits, and
    a missing count is expressible (`total_matched=None`) while a raised error
    would throw away rows that were fetched successfully. Only the two documented
    outcomes of :func:`run_query` are swallowed — anything else is a bug in this
    module and must not be disguised as «the store did not answer».
    """
    try:
        rows = await run_query(
            http,
            queries.count_cubes(query, language, creator_uri),
            timeout_s=COUNT_BUDGET_S,
            total_budget=COUNT_BUDGET_S,
        )
    except (SparqlError, UpstreamError):
        return None
    if not rows or rows[0].get("n") is None:
        return None
    try:
        return int(rows[0]["n"])
    except (TypeError, ValueError):
        # SPARQL hands the aggregate over as a string; anything that is not a
        # number means the shape of the answer changed, and inventing a total
        # from it would be worse than admitting we have none.
        return None


async def search(
    http: httpx.AsyncClient,
    *,
    query: str,
    language: str,
    creator_uri: str | None,
    limit: int,
    latest_only: bool,
) -> dict[str, Any]:
    """Search cubes and say how complete the answer is.

    Returns ``{"cubes": [...], "total_matched": int | None, "truncated": bool}``.
    ``returned`` on its own cannot distinguish «that is all there is» from «that
    is the first page», and a caller who cannot tell stops at the page it got.

    **`truncated` is the load-bearing field, and it errs towards True.** False
    means: everything that matched is in `cubes`. True means: there is more, or
    there may be more and this layer could not rule it out. The asymmetry is
    deliberate — a wrong True costs a second query, a wrong False costs the
    caller the rest of the result set without telling it.

    Three routes to the two numbers, in order of preference:

    1. **The store was not capped.** One extra row is fetched beyond what is
       needed (`+ 1`), so a full page is distinguishable from a complete one. If
       fewer rows came back than were asked for, this layer has seen every
       matching row, and `total_matched` is simply the length of the processed
       list — exact, free, and on the same unit as `cubes` in both branches.
    2. **Capped, and `latest_only=False`.** Rows are cube versions here, which is
       what `queries.count_cubes` counts, so a second query answers it exactly.
    3. **Capped, and `latest_only=True`.** `total_matched` stays None, and this
       is the case the obvious implementation gets wrong. Measured live on
       2026-09-20, German labels: «wald» matches 127 cubes but collapses to 35
       logical ones, «energie» 33 to 13. Reporting 127 next to a `returned` of
       20 would tell a caller it is missing 107 cubes when at most 15 exist for
       it to find. The count LINDAS can give cheaply is a count of versions; no
       cheap query expresses the version-collapse heuristic in
       `_base_cube_uri`. None says «unknown», which is true, where 127 would say
       something false.

    Where an exact `total_matched` exists, `truncated` is derived from it rather
    than from the cap: the store being capped does not by itself mean rows were
    withheld from `cubes` — the status filter below can shrink a capped page to
    fewer hits than the total.
    """
    # Over-fetch when deduplicating, because several rows may collapse into one.
    # The `+ 1` is what makes truncation observable: without it, a page that is
    # exactly full and a result set that is exactly exhausted look identical.
    fetch = limit * 4 + 1 if latest_only else limit + 1
    rows = await run_query(http, queries.search_cubes(query, language, creator_uri, fetch))
    store_capped = len(rows) >= fetch

    published = [r for r in rows if r.get("status", "").endswith("Published") or "status" not in r]

    if latest_only:
        newest: dict[str, dict[str, Any]] = {}
        for row in published:
            base = _base_cube_uri(row["cube"])
            current = newest.get(base)
            if current is None or _version_key(row) > _version_key(current):
                newest[base] = row
        candidates = sorted(newest.values(), key=_version_key, reverse=True)
    else:
        candidates = published

    hits = candidates[:limit]

    if not store_capped:
        total: int | None = len(candidates)
    elif not latest_only:
        total = await _count_matches(http, query=query, language=language, creator_uri=creator_uri)
    else:
        total = None

    truncated = total > len(hits) if total is not None else True

    return {"cubes": hits, "total_matched": total, "truncated": truncated}


def _version_key(row: dict[str, Any]) -> tuple:
    """Sortable version key. Falls back to the URI so order is deterministic."""
    version = row.get("version") or ""
    parts = tuple(int(p) for p in re.findall(r"\d+", version))
    return (parts, row.get("cube", ""))


async def get_structure(http: httpx.AsyncClient, *, cube_uri: str, language: str) -> dict[str, Any]:
    """Phase 1: read a cube's dimensions and measures plus its metadata."""
    meta_rows = await run_query(http, queries.cube_metadata(cube_uri, language))
    meta = meta_rows[0] if meta_rows else {}

    dim_rows = await run_query(http, queries.cube_dimensions(cube_uri, language))
    dimensions = []
    for row in dim_rows:
        kind = _local_name(row.get("kind", "")) or "Dimension"
        has_codelist = str(row.get("has_codelist", "")).lower() in {"true", "1"}
        dimensions.append(
            {
                "path": row["path"],
                "name": row.get("name") or _local_name(row["path"]),
                "kind": kind,
                "has_codelist": has_codelist,
            }
        )

    return {
        "cube_uri": cube_uri,
        "name": meta.get("name"),
        "description": meta.get("desc"),
        "creator": meta.get("creator"),
        "creator_name": _local_name(meta.get("creator", "")),
        "version": meta.get("version"),
        "status": _local_name(meta.get("status", "")),
        "licence": meta.get("license"),
        "dimensions": dimensions,
    }


async def get_codelist(
    http: httpx.AsyncClient, *, cube_uri: str, dimension_path: str, language: str
) -> dict[str, str]:
    """Return {value_uri: label} for one dimension's code list.

    Used internally to resolve observation codes. The label falls back to the
    identifier, then to the URI's local name, so a value is never blank.
    """
    rows = await run_query(http, queries.dimension_codelist(cube_uri, dimension_path, language))
    mapping: dict[str, str] = {}
    for row in rows:
        value = row.get("value")
        if not value:
            continue
        label = row.get("label") or row.get("ident") or _local_name(value)
        mapping[value] = label
    return mapping


async def get_observations(
    http: httpx.AsyncClient,
    *,
    cube_uri: str,
    language: str,
    limit: int,
    resolve_labels: bool,
) -> dict[str, Any]:
    """Phase 2: fetch observations with codes resolved to labels.

    Groups the flat (obs, predicate, value) triples back into one dict per
    observation, then — if requested — replaces coded URI values with their
    human labels using each dimension's code list.
    """
    structure = await get_structure(http, cube_uri=cube_uri, language=language)
    dim_by_path = {d["path"]: d for d in structure["dimensions"]}

    # Fetch a few triples per observation, so scale the raw limit up.
    triple_limit = limit * max(len(dim_by_path), 1) * 2
    rows = await run_query(http, queries.cube_observations(cube_uri, triple_limit))

    grouped: dict[str, dict[str, str]] = {}
    for row in rows:
        obs = row.get("obs")
        pred = row.get("p")
        val = row.get("o")
        if not obs or not pred:
            continue
        grouped.setdefault(obs, {})[pred] = val

    codelists: dict[str, dict[str, str]] = {}
    if resolve_labels:
        for path, dim in dim_by_path.items():
            if dim["has_codelist"]:
                codelists[path] = await get_codelist(
                    http, cube_uri=cube_uri, dimension_path=path, language=language
                )

    observations = []
    for _obs_uri, preds in list(grouped.items())[:limit]:
        record: dict[str, Any] = {}
        for pred, val in preds.items():
            # Drop the rdf:type triple — it is structural noise, not data.
            if pred.endswith("22-rdf-syntax-ns#type"):
                continue
            dim = dim_by_path.get(pred)
            label = dim["name"] if dim else _local_name(pred)
            resolved = val
            if resolve_labels and pred in codelists and val in codelists[pred]:
                resolved = codelists[pred][val]
            elif resolve_labels and isinstance(val, str) and "/canton/" in val:
                # Cantons are coded as ld.admin.ch/canton/<n> even without an
                # sh:in list; expose the bare number rather than the URI.
                resolved = _local_name(val)
            record[label] = resolved
        observations.append(record)

    return {
        "cube_uri": cube_uri,
        "cube_name": structure["name"],
        "licence": structure["licence"],
        "labels_resolved": resolve_labels,
        "returned": len(observations),
        "observations": observations,
    }


async def list_publishers(http: httpx.AsyncClient) -> list[dict[str, Any]]:
    rows = await run_query(http, queries.list_creators())
    return [
        {
            "creator_uri": r["creator"],
            "name": _local_name(r["creator"]),
            "cube_count": int(r.get("cubes", 0)),
        }
        for r in rows
        if r.get("creator")
    ]


async def resolve_municipality(
    http: httpx.AsyncClient, *, name_or_bfs: str, language: str
) -> list[dict[str, Any]]:
    """Resolve a municipality name or BFS number to its URI and identifier."""
    if name_or_bfs.strip().isdigit():
        rows = await run_query(http, queries.resolve_municipality_by_bfs(int(name_or_bfs.strip())))
    else:
        rows = await run_query(http, queries.resolve_municipality_by_name(name_or_bfs, language))
    return [
        {
            "uri": r["muni"],
            "name": r.get("name"),
            "bfs_number": r.get("ident") or _local_name(r["muni"]),
        }
        for r in rows
        if r.get("muni")
    ]
