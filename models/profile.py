"""Dynamic collection generation from user-provided keywords.

When users enter custom keywords via GitHub Actions, this module
creates CollectionConfig objects on the fly — no code changes needed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.collection import CollectionConfig, SearchQuery


class SearchProfile(BaseModel):
    """Dynamic search profile from user keywords."""

    keywords: Annotated[list[str], Field(description="List of search keywords")]
    quality_tier: Annotated[str, Field(default="all", description="Q1, Q2, Q3, Q4, or all")]
    years_back: Annotated[int, Field(default=5, ge=0, description="Years back from current year")]
    max_results: Annotated[int, Field(default=5, ge=1, le=100, description="Results per query")]

    model_config = ConfigDict(extra="forbid")

    # Quality tier → SJR threshold mapping
    QUALITY_THRESHOLDS: dict[str, float] = {
        "Q1": 50.0,
        "Q2": 20.0,
        "Q3": 5.0,
        "Q4": 0.0,
        "all": 0.0,
    }

    def build_collection(self) -> CollectionConfig:
        """Build a CollectionConfig from keywords.

        Each keyword generates 3 queries (arXiv, OpenAlex, Crossref).
        """
        queries = []
        for kw in self.keywords:
            kw = kw.strip()
            if not kw:
                continue

            queries.extend([
                SearchQuery(
                    query=kw,
                    connector="arxiv",
                    max_results=self.max_results,
                    extra_filters={"cat": "cond-mat.mtrl-sci"},
                    description=f"arXiv: {kw} in cond-mat materials science",
                ),
                SearchQuery(
                    query=kw,
                    connector="openalex",
                    max_results=self.max_results,
                    description=f"OpenAlex: {kw}",
                ),
                SearchQuery(
                    query=kw,
                    connector="crossref",
                    max_results=self.max_results,
                    extra_filters={"type": "journal-article"},
                    description=f"Crossref: {kw} journal articles",
                ),
            ])

        # Generate a deterministic collection name from keywords
        name = self._generate_name()
        year_from = datetime.now().year - self.years_back if self.years_back > 0 else 0
        min_cites = self.QUALITY_THRESHOLDS.get(self.quality_tier, 0.0)

        return CollectionConfig(
            name=name,
            display_name=f"Custom: {', '.join(self.keywords)}",
            domain="materials-science",
            description=f"Dynamic collection for keywords: {', '.join(self.keywords)}",
            queries=queries,
            enabled_connectors=["arxiv", "openalex", "crossref", "unpaywall"],
            max_total_papers=0,  # Unlimited
            year_from=year_from,
            min_journal_cites_per_year=min_cites if self.quality_tier != "all" else 0.0,
        )

    def _generate_name(self) -> str:
        """Generate a deterministic, filesystem-safe collection name."""
        combined = "-".join(kw.lower().replace(" ", "-") for kw in self.keywords)
        # Shorten if too long (filesystem limit ~255 chars)
        if len(combined) > 80:
            digest = hashlib.md5(combined.encode()).hexdigest()[:8]
            return f"custom-{digest}"
        return f"custom-{combined}"


def parse_keywords(keywords_str: str) -> Optional[SearchProfile]:
    """Parse comma-separated keywords string into a SearchProfile.

    Returns None if the string is empty.
    """
    if not keywords_str or not keywords_str.strip():
        return None

    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    if not keywords:
        return None

    return SearchProfile(keywords=keywords)
