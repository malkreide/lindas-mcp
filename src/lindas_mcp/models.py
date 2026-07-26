"""Pydantic v2 response models for lindas-mcp."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .lindas.client import ATTRIBUTION

Provenance = Literal["live_sparql"]


class LindasResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default=ATTRIBUTION)
    provenance: Provenance = Field(default="live_sparql")
    retrieved_at: str


class CubeHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cube_uri: str
    name: str | None = None
    description: str | None = None
    creator: str | None = None
    version: str | None = None
    status: str | None = None


class CubeSearchResult(LindasResponse):
    query: str | None
    language: str
    latest_only: bool
    returned: int
    cubes: list[CubeHit]


class Dimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    name: str
    kind: str = Field(description="KeyDimension, MeasureDimension or Dimension.")
    has_codelist: bool


class CubeStructureResult(LindasResponse):
    cube_uri: str
    name: str | None = None
    description: str | None = None
    creator_name: str | None = None
    version: str | None = None
    status: str | None = None
    licence: str | None = Field(
        default=None, description="Often a Fedlex URI — joins to fedlex-mcp."
    )
    dimensions: list[Dimension]


class ObservationsResult(LindasResponse):
    cube_uri: str
    cube_name: str | None = None
    licence: str | None = None
    labels_resolved: bool
    returned: int
    observations: list[dict[str, Any]]


class Publisher(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creator_uri: str
    name: str
    cube_count: int


class PublisherListResult(LindasResponse):
    returned: int
    publishers: list[Publisher]


class Municipality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str
    name: str | None = None
    bfs_number: str | None = Field(
        default=None, description="BFS commune number — the portfolio join key."
    )


class MunicipalityResult(LindasResponse):
    query: str
    returned: int
    municipalities: list[Municipality]


class SparqlResult(LindasResponse):
    row_count: int
    rows: list[dict[str, Any]]
    note: str


class StatusResult(LindasResponse):
    reachable: bool
    endpoint: str
    cube_count: int | None = None
    last_successful_call: str | None = None
    note: str
