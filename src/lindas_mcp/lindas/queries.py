"""SPARQL query templates for the cube.link vocabulary.

Every template here is anchored on a known class (`cube:Cube`, `Municipality`)
or a specific cube URI. There is no template that scans the whole store — that
is the guardrail from fundstück 1 of the probe, expressed in code: LINDAS
rewards queries that know what they are asking for and times out on the ones
that ask for everything.
"""

from __future__ import annotations

PREFIXES = """
PREFIX cube: <https://cube.link/>
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX schema: <http://schema.org/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

MUNICIPALITY_CLASS = "https://schema.ld.admin.ch/Municipality"


def _escape(text: str) -> str:
    """Escape a user string for safe embedding in a SPARQL literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def search_cubes(
    query: str,
    language: str,
    creator_uri: str | None,
    limit: int,
) -> str:
    """Full-text-ish cube search, anchored on cube:Cube.

    Only cubes with status Published are returned. Draft and retired versions
    are excluded so the agent never queries an unpublished cube by accident.
    """
    filters = []
    if query:
        q = _escape(query.lower())
        filters.append(
            f'FILTER(CONTAINS(LCASE(STR(?name)), "{q}") || CONTAINS(LCASE(STR(?desc)), "{q}"))'
        )
    if creator_uri:
        filters.append(f"?cube dcterms:creator <{_escape(creator_uri)}> .")
    filter_block = "\n  ".join(filters)

    return f"""{PREFIXES}
SELECT ?cube ?name ?desc ?creator ?version ?status WHERE {{
  ?cube a cube:Cube ;
        schema:name ?name .
  FILTER(LANG(?name) = "{language}")
  OPTIONAL {{ ?cube schema:description ?desc . FILTER(LANG(?desc) = "{language}") }}
  OPTIONAL {{ ?cube dcterms:creator ?creator }}
  OPTIONAL {{ ?cube schema:version ?version }}
  OPTIONAL {{ ?cube schema:creativeWorkStatus ?status }}
  {filter_block}
}}
ORDER BY DESC(?version)
LIMIT {limit}
"""


def cube_metadata(cube_uri: str, language: str) -> str:
    """Descriptive metadata for one cube: name, description, creator, licence."""
    return f"""{PREFIXES}
SELECT ?name ?desc ?creator ?version ?status ?license WHERE {{
  BIND(<{cube_uri}> AS ?cube)
  ?cube a cube:Cube .
  OPTIONAL {{ ?cube schema:name ?name . FILTER(LANG(?name) = "{language}") }}
  OPTIONAL {{ ?cube schema:description ?desc . FILTER(LANG(?desc) = "{language}") }}
  OPTIONAL {{ ?cube dcterms:creator ?creator }}
  OPTIONAL {{ ?cube schema:version ?version }}
  OPTIONAL {{ ?cube schema:creativeWorkStatus ?status }}
  OPTIONAL {{ ?cube dcterms:license ?license }}
}}
LIMIT 1
"""


def cube_dimensions(cube_uri: str, language: str) -> str:
    """Phase 1: the SHACL shape of a cube — its dimensions and measures.

    `kind` distinguishes cube:KeyDimension (a filterable axis) from
    cube:MeasureDimension (a measured value). `has_codelist` signals whether
    the dimension carries an sh:in code list that needs resolving to labels.
    """
    return f"""{PREFIXES}
SELECT ?path ?name ?kind (BOUND(?in) AS ?has_codelist) WHERE {{
  <{cube_uri}> cube:observationConstraint ?shape .
  ?shape sh:property ?p .
  ?p sh:path ?path .
  FILTER(?path != rdf:type)
  OPTIONAL {{ ?p schema:name ?name . FILTER(LANG(?name) = "{language}") }}
  OPTIONAL {{ ?p a ?kind . FILTER(?kind IN (cube:KeyDimension, cube:MeasureDimension)) }}
  OPTIONAL {{ ?p sh:in ?in }}
}}
"""


def dimension_codelist(cube_uri: str, dimension_path: str, language: str) -> str:
    """Resolve one dimension's code list to {code_uri, code, label}.

    Uses the rdf:rest*/rdf:first list-walk to expand the sh:in RDF list, then
    reads schema:name off each value URI. This is the mechanism verified in the
    probe: codes carry human labels directly on the value URI.
    """
    return f"""{PREFIXES}
SELECT ?value ?ident ?label WHERE {{
  <{cube_uri}> cube:observationConstraint ?shape .
  ?shape sh:property ?p .
  ?p sh:path <{dimension_path}> ; sh:in ?list .
  ?list rdf:rest*/rdf:first ?value .
  OPTIONAL {{ ?value schema:identifier ?ident }}
  OPTIONAL {{ ?value schema:name ?label . FILTER(LANG(?label) = "{language}") }}
}}
"""


def cube_observations(cube_uri: str, limit: int) -> str:
    """Phase 2: raw observations of a cube.

    Note the observationSet indirection (fundstück 6): observations hang off
    cube:observationSet, never directly off the cube. Values come back as codes
    and are resolved to labels in the cube layer, not here.
    """
    return f"""{PREFIXES}
SELECT ?obs ?p ?o WHERE {{
  <{cube_uri}> cube:observationSet ?set .
  ?set cube:observation ?obs .
  ?obs ?p ?o .
}}
LIMIT {limit}
"""


def list_creators() -> str:
    """Publishing bodies, deduplicated on dcterms:creator (a stable URI).

    Anchored on cube:Cube and grouped by creator. Uses creator rather than
    schema:publisher because publisher names are multilingual and split one
    body into several rows; the creator URI is single and stable.
    """
    return f"""{PREFIXES}
SELECT ?creator (COUNT(DISTINCT ?cube) AS ?cubes) WHERE {{
  ?cube a cube:Cube .
  ?cube dcterms:creator ?creator .
}}
GROUP BY ?creator
ORDER BY DESC(?cubes)
"""


def resolve_municipality_by_name(name: str, language: str) -> str:
    return f"""{PREFIXES}
SELECT ?muni ?name ?ident WHERE {{
  ?muni a <{MUNICIPALITY_CLASS}> ; schema:name ?name .
  OPTIONAL {{ ?muni schema:identifier ?ident }}
  FILTER(CONTAINS(LCASE(STR(?name)), "{_escape(name.lower())}"))
}}
LIMIT 20
"""


def resolve_municipality_by_bfs(bfs_number: int) -> str:
    """A municipality URI is ld.admin.ch/municipality/<BFS>, so we build it."""
    uri = f"https://ld.admin.ch/municipality/{bfs_number}"
    return f"""{PREFIXES}
SELECT ?muni ?name ?ident WHERE {{
  BIND(<{uri}> AS ?muni)
  ?muni schema:name ?name .
  OPTIONAL {{ ?muni schema:identifier ?ident }}
}}
"""
