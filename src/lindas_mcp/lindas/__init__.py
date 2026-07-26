"""LINDAS access layer — extraction-ready.

Three layers, strictly separated:
  client.py  — SPARQL over HTTP, knows nothing about cubes
  queries.py — SPARQL templates, all anchored on a known class
  cube.py    — the cube.link vocabulary guardrail and two-phase access

Only cube.py is imported by the server tools. This is the module that lifts
into other LINDAS-backed servers unchanged.
"""

from .client import ATTRIBUTION, ENDPOINT, SparqlError, UpstreamError

__all__ = ["ATTRIBUTION", "ENDPOINT", "SparqlError", "UpstreamError"]
