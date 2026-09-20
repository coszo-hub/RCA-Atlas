from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchRequest(StrictModel):
    query: str = Field(min_length=2, max_length=1_000)
    limit: int = Field(default=10, ge=1, le=50)
    lexical_weight: float = Field(default=0.45, ge=0, le=1)
    vector_weight: float = Field(default=0.55, ge=0, le=1)
    collection_ids: list[str] = Field(default_factory=list, max_length=20)


class ContextRequest(SearchRequest):
    graph_hops: int = Field(default=1, ge=0, le=3)
    neighbors_per_seed: int = Field(default=8, ge=1, le=25)
    tool_limit: int = Field(default=3, ge=0, le=10)


class NodeSeed(StrictModel):
    collection_id: str = Field(min_length=1, max_length=100)
    local_id: str = Field(min_length=1, max_length=500)


class NeighborsRequest(StrictModel):
    seeds: list[NodeSeed] = Field(min_length=1, max_length=20)
    hops: int = Field(default=1, ge=1, le=3)
    limit: int = Field(default=25, ge=1, le=100)


class ToolsRequest(StrictModel):
    query: str = Field(min_length=2, max_length=1_000)
    limit: int = Field(default=5, ge=1, le=20)


class Citation(BaseModel):
    source_id: str
    title: str
    url: Optional[str] = None


class SearchHit(BaseModel):
    chunk_id: str
    collection_id: str
    title: str
    text: str
    score: float
    lexical_score: float
    vector_score: float
    citations: list[Citation]
    metadata: dict[str, Any] = Field(default_factory=dict)


class Neighbor(BaseModel):
    collection_id: str
    local_id: str
    name: str
    depth: int
    direction: str
    predicate: str
    source_url: Optional[str] = None


class ToolHint(BaseModel):
    collection_id: str
    name: str
    description: str
    score: float
    required_arguments: list[str]
    input_schema: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class ContextResponse(SearchResponse):
    neighbors: list[Neighbor]
    tool_hints: list[ToolHint]


class NeighborsResponse(BaseModel):
    neighbors: list[Neighbor]


class ToolsResponse(BaseModel):
    query: str
    tool_hints: list[ToolHint]
