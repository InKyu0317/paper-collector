"""Dynamic collection generation from user-provided keywords.

When users enter custom keywords via GitHub Actions, this module
creates CollectionConfig objects on the fly — no code changes needed.

Two modes:
- Standalone keyword search: `build_collection()` — keyword only.
- Preset × keyword intersection: `build_intersected_collection(preset)` —
  combines the preset's `search_topic` with each keyword via per-API AND syntax,
  and stores results into the preset's existing collection folder.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.collection import CollectionConfig, SearchQuery

# Quality tier → SJR threshold mapping (heuristic fallback only;
# real SJR quartile filtering happens in CollectionEngine via AppConfig.quality_tier).
QUALITY_THRESHOLDS: dict[str, float] = {
    "Q1": 50.0,
    "Q2": 20.0,
    "Q3": 5.0,
    "Q4": 0.0,
    "all": 0.0,
}


def _combine_query(topic: str, keyword: str, connector: str) -> str:
    """Combine a collection topic with a user keyword using each API's AND syntax.

    `topic` MUST be a plain natural-language phrase (e.g. "halide solid-state
    battery"), NOT a boolean expression. Boolean expressions like
    `halide AND (solid-state battery OR solid electrolyte)` belong in the
    preset's per-connector `queries[*].query` (used in preset-only mode), not
    in `search_topic` (used in intersection mode), because:

    - Crossref does not support boolean operators in its `query` parameter -
      AND/OR/parentheses would be sent as literal search tokens, polluting
      the ranking.
    - arXiv and OpenAlex DO support booleans, but mixing a boolean topic with
      a plain keyword via outer AND creates fragile precedence that is hard
      to keep correct across the three APIs simultaneously.

    Per-connector handling:
    - arXiv: `(topic) AND (keyword)` - uppercase boolean, parens force grouping.
    - OpenAlex: `(topic) AND (keyword)` - same; OpenAlex supports parens too.
    - Crossref: `topic keyword` - space-joined; Crossref ANDs space-separated
      terms implicitly (https://github.com/CrossRef/rest-api-doc).
    """
    topic = topic.strip()
    keyword = keyword.strip()
    if not topic:
        return keyword
    if not keyword:
        return topic
    if connector == "arxiv":
        return f"({topic}) AND ({keyword})"
    if connector == "openalex":
        return f"({topic}) AND ({keyword})"
    # crossref and any unknown connector: plain concatenation (implicit AND)
    return f"{topic} {keyword}"


class SearchProfile(BaseModel):
    """Dynamic search profile from user keywords."""

    keywords: Annotated[list[str], Field(description="List of search keywords")]
    quality_tier: Annotated[str, Field(default="all", description="Q1, Q2, Q3, Q4, or all")]
    years_back: Annotated[int, Field(default=5, ge=0, description="Years back from current year")]
    max_results: Annotated[int, Field(default=5, ge=1, le=100, description="Results per query")]

    model_config = ConfigDict(extra="forbid")

    def _build_queries(self, base_topic: str = "") -> list[SearchQuery]:
        """Build per-keyword search queries across 3 connectors, optionally
        combined with a base_topic via per-API AND syntax."""
        queries: list[SearchQuery] = []
        for kw_raw in self.keywords:
            kw = kw_raw.strip()
            if not kw:
                continue

            arxiv_q = _combine_query(base_topic, kw, "arxiv")
            openalex_q = _combine_query(base_topic, kw, "openalex")
            crossref_q = _combine_query(base_topic, kw, "crossref")

            label = f"{base_topic} + {kw}" if base_topic else kw
            queries.extend([
                SearchQuery(
                    query=arxiv_q,
                    connector="arxiv",
                    max_results=self.max_results,
                    extra_filters={"cat": "cond-mat.mtrl-sci"},
                    description=f"arXiv: {label} in cond-mat materials science",
                ),
                SearchQuery(
                    query=openalex_q,
                    connector="openalex",
                    max_results=self.max_results,
                    description=f"OpenAlex: {label}",
                ),
                SearchQuery(
                    query=crossref_q,
                    connector="crossref",
                    max_results=self.max_results,
                    extra_filters={"type": "journal-article"},
                    description=f"Crossref: {label} journal articles",
                ),
            ])
        return queries

    def build_collection(self) -> CollectionConfig:
        """Build a standalone keyword-only collection (no preset topic).

        Used when the user supplies keywords without selecting any preset.
        Results are stored under a generated `custom-<keywords>` folder.
        """
        queries = self._build_queries(base_topic="")
        name = self._generate_name()
        year_from = datetime.now().year - self.years_back if self.years_back > 0 else 0
        min_cites = QUALITY_THRESHOLDS.get(self.quality_tier, 0.0)

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

    def build_intersected_collection(self, preset: CollectionConfig) -> CollectionConfig:
        """Build a collection that intersects the preset's topic with user keywords.

        - Each (keyword × connector) query is rewritten as `(preset_topic) AND (keyword)`
          using per-API AND syntax.
        - Results are stored INTO the preset's existing collection folder so the user
          gets a single coherent set of papers matching `topic AND keyword`.
        - Preset-level fields (year_from, quality filters, whitelist) are preserved;
          profile years_back overrides preset year_from only when explicitly set.
        """
        # Preset must expose a search_topic for combination; fall back to display_name
        # or the preset name if absent.
        base_topic = (preset.search_topic or preset.display_name or preset.name).strip()
        queries = self._build_queries(base_topic=base_topic)

        # Profile year_from overrides preset only when years_back > 0 (explicit value).
        year_from = (
            datetime.now().year - self.years_back if self.years_back > 0 else preset.year_from
        )

        return CollectionConfig(
            name=preset.name,  # store into the SAME folder as the preset
            display_name=f"{preset.display_name} ∩ {', '.join(self.keywords)}",
            domain=preset.domain,
            description=f"{preset.name} intersected with keywords: {', '.join(self.keywords)}",
            queries=queries,
            enabled_connectors=preset.enabled_connectors,
            max_total_papers=preset.max_total_papers,
            year_from=year_from,
            min_journal_cites_per_year=preset.min_journal_cites_per_year,
            min_paper_citation_count=preset.min_paper_citation_count,
            journal_whitelist=preset.journal_whitelist,
        )

    def _generate_name(self) -> str:
        """Generate a deterministic, filesystem-safe collection name."""
        combined = "-".join(kw.lower().replace(" ", "-") for kw in self.keywords)
        # Shorten if too long (filesystem limit ~255 chars)
        if len(combined) > 80:
            digest = hashlib.md5(combined.encode()).hexdigest()[:8]
            return f"custom-{digest}"
        return f"custom-{combined}"


def parse_keywords(
    keywords_str: str,
    quality_tier: str = "all",
    years_back: int = 5,
    max_results: int = 5,
) -> Optional[SearchProfile]:
    """Parse comma-separated keywords string into a SearchProfile.

    Returns None if the string is empty.
    Accepts overrides for quality_tier / years_back / max_results so callers can
    forward env-driven values (otherwise the profile uses field defaults).
    """
    if not keywords_str or not keywords_str.strip():
        return None

    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    if not keywords:
        return None

    return SearchProfile(
        keywords=keywords,
        quality_tier=quality_tier,
        years_back=years_back,
        max_results=max_results,
    )
