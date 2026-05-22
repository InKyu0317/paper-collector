"""Collection configuration and search query definitions.

Each collection defines search queries, enabled connectors,
and output-specific metadata for the materials science domain.
"""

from __future__ import annotations

import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class SearchQuery(BaseModel):
    """A single search query for a collection."""

    query: Annotated[str, Field(description="Search string in the source API's native syntax")]
    connector: Annotated[str, Field(default="arxiv", description="Connector name: arxiv, openalex, crossref")]
    max_results: Annotated[int, Field(default=5, ge=1, le=100)]
    extra_filters: Annotated[dict[str, str], Field(default_factory=dict)]
    description: Annotated[str, Field(default="")]

    model_config = ConfigDict(extra="forbid")


class CollectionConfig(BaseModel):
    """Configuration for a single paper collection."""

    name: Annotated[str, Field(description="Unique collection identifier e.g. 'aluminosilicate'")]
    display_name: Annotated[str, Field(default="")]
    domain: Annotated[str, Field(default="materials-science")]
    description: Annotated[str, Field(default="")]
    # Topic phrase used to intersect the preset with user-provided keywords
    # (combined per-API via `(topic) AND (keyword)` etc.). Should be a concise
    # noun phrase, NOT a full boolean query.
    search_topic: Annotated[str, Field(default="", description="Plain natural-language topic phrase for AND-combining with user keywords in intersection mode (e.g. 'halide solid-state battery'). MUST NOT contain boolean operators or parentheses - those belong in queries[*].query.")]
    queries: Annotated[list[SearchQuery], Field(default_factory=list)]
    enabled_connectors: Annotated[list[str], Field(default_factory=lambda: ["arxiv", "openalex", "crossref", "unpaywall"])]
    max_total_papers: Annotated[int, Field(default=100_000, ge=0, description="Max papers per collection. 0 = unlimited.")]

    # Time range filter
    year_from: Annotated[int, Field(default_factory=lambda: datetime.datetime.now().year - 5, ge=1900, description="Collect papers from this year onwards")]

    # Quality filters (disabled by default; set >0 to enable)
    min_journal_cites_per_year: Annotated[float, Field(default=0.0, ge=0.0, description="Minimum journal cites/year (Q1 approx 50+)")]
    min_paper_citation_count: Annotated[int, Field(default=0, ge=0, description="Minimum paper citation count")]
    journal_whitelist: Annotated[list[str], Field(default_factory=list, description="Only accept papers from these journals")]

    model_config = ConfigDict(extra="forbid")


# ── Pre-configured collections ────────────────────────────────────────────

ALUMINOSILICATE_CONFIG = CollectionConfig(
    name="aluminosilicate",
    display_name="Aluminosilicate Materials",
    domain="materials-science",
    description="Research on aluminosilicate synthesis, characterization, and applications",
    search_topic="aluminosilicate",
    queries=[
        SearchQuery(
            query="aluminosilicate",
            connector="arxiv",
            max_results=5,
            extra_filters={"cat": "cond-mat.mtrl-sci"},
            description="arXiv: aluminosilicate in cond-mat materials science",
        ),
        SearchQuery(
            query="aluminosilicate materials synthesis characterization",
            connector="openalex",
            max_results=5,
            description="OpenAlex: recent OA aluminosilicate research",
        ),
        SearchQuery(
            query="aluminosilicate zeolite geopolymer materials",
            connector="crossref",
            max_results=5,
            extra_filters={"type": "journal-article"},
            description="Crossref: aluminosilicate journal articles",
        ),
    ],
    enabled_connectors=["arxiv", "openalex", "crossref", "unpaywall"],
    max_total_papers=0,  # Unlimited
    # Quality filters (disabled by default; set >0 to enable Q1 filtering)
    # min_journal_cites_per_year=50.0,
    # min_paper_citation_count=10,
)

HALIDE_BATTERY_CONFIG = CollectionConfig(
    name="halide-solid-state-battery",
    display_name="Halide Solid-State Battery",
    domain="materials-science",
    description="Research on halide-based solid electrolytes and all-solid-state batteries",
    search_topic="halide solid-state battery",
    queries=[
        SearchQuery(
            query="halide AND (solid-state battery OR solid electrolyte)",
            connector="arxiv",
            max_results=5,
            extra_filters={"cat": "cond-mat.mtrl-sci"},
            description="arXiv: halide solid-state battery in cond-mat",
        ),
        SearchQuery(
            query="halide solid electrolyte all-solid-state battery lithium",
            connector="openalex",
            max_results=5,
            description="OpenAlex: recent halide battery OA papers",
        ),
        SearchQuery(
            query="halide solid state electrolyte battery lithium",
            connector="crossref",
            max_results=5,
            extra_filters={"type": "journal-article"},
            description="Crossref: halide battery journal articles",
        ),
    ],
    enabled_connectors=["arxiv", "openalex", "crossref", "unpaywall"],
    max_total_papers=0,  # Unlimited
    # Quality filters (disabled by default; set >0 to enable Q1 filtering)
    # min_journal_cites_per_year=50.0,
    # min_paper_citation_count=10,
)

DEFAULT_COLLECTIONS: dict[str, CollectionConfig] = {
    "aluminosilicate": ALUMINOSILICATE_CONFIG,
    "halide-solid-state-battery": HALIDE_BATTERY_CONFIG,
}
