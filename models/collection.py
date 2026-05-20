"""Collection configuration and search query definitions.

Each collection defines search queries, enabled connectors,
and output-specific metadata for the materials science domain.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field


class SearchQuery(BaseModel):
    """A single search query for a collection."""

    query: Annotated[str, Field(description="Search string in the source API's native syntax")]
    connector: Annotated[str, Field(default="arxiv", description="Connector name: arxiv, openalex, crossref")]
    max_results: Annotated[int, Field(default=50, ge=1, le=500)]
    extra_filters: Annotated[dict[str, str], Field(default_factory=dict)]
    description: Annotated[str, Field(default="")]

    model_config = ConfigDict(extra="forbid")


class CollectionConfig(BaseModel):
    """Configuration for a single paper collection."""

    name: Annotated[str, Field(description="Unique collection identifier e.g. 'aluminosilicate'")]
    display_name: Annotated[str, Field(default="")]
    domain: Annotated[str, Field(default="materials-science")]
    description: Annotated[str, Field(default="")]
    queries: Annotated[list[SearchQuery], Field(default_factory=list)]
    enabled_connectors: Annotated[list[str], Field(default_factory=lambda: ["arxiv", "openalex", "crossref", "unpaywall"])]
    max_total_papers: Annotated[int, Field(default=10_000, ge=0)]

    model_config = ConfigDict(extra="forbid")


# ── Pre-configured collections ────────────────────────────────────────────

ALUMINOSILICATE_CONFIG = CollectionConfig(
    name="aluminosilicate",
    display_name="Aluminosilicate Materials",
    domain="materials-science",
    description="Research on aluminosilicate synthesis, characterization, and applications",
    queries=[
        SearchQuery(
            query="aluminosilicate OR aluminosilicate materials synthesis",
            connector="arxiv",
            max_results=100,
            extra_filters={"cat": "cond-mat.mtrl-sci"},
            description="arXiv: aluminosilicate in cond-mat materials science",
        ),
        SearchQuery(
            query="aluminosilicate materials synthesis characterization",
            connector="openalex",
            max_results=100,
            extra_filters={"publication_year": "2020"},
            description="OpenAlex: recent OA aluminosilicate research",
        ),
        SearchQuery(
            query="aluminosilicate zeolite geopolymer materials",
            connector="crossref",
            max_results=50,
            extra_filters={"type": "journal-article"},
            description="Crossref: aluminosilicate journal articles",
        ),
    ],
    enabled_connectors=["arxiv", "openalex", "crossref", "unpaywall"],
)

HALIDE_BATTERY_CONFIG = CollectionConfig(
    name="halide-solid-state-battery",
    display_name="Halide Solid-State Battery",
    domain="materials-science",
    description="Research on halide-based solid electrolytes and all-solid-state batteries",
    queries=[
        SearchQuery(
            query="halide solid state battery OR halide electrolyte all solid state battery",
            connector="arxiv",
            max_results=100,
            extra_filters={"cat": "cond-mat.mtrl-sci"},
            description="arXiv: halide solid-state battery in cond-mat",
        ),
        SearchQuery(
            query="halide solid electrolyte all-solid-state battery lithium",
            connector="openalex",
            max_results=100,
            extra_filters={"publication_year": "2020"},
            description="OpenAlex: recent halide battery OA papers",
        ),
        SearchQuery(
            query="halide solid state electrolyte battery lithium",
            connector="crossref",
            max_results=50,
            extra_filters={"type": "journal-article"},
            description="Crossref: halide battery journal articles",
        ),
    ],
    enabled_connectors=["arxiv", "openalex", "crossref", "unpaywall"],
)

DEFAULT_COLLECTIONS: dict[str, CollectionConfig] = {
    "aluminosilicate": ALUMINOSILICATE_CONFIG,
    "halide-solid-state-battery": HALIDE_BATTERY_CONFIG,
}
