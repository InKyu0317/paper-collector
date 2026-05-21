"""OpenAlex API connector.

Provides search over the comprehensive OpenAlex catalog of research works.
Requires an API key (free) for production use.
"""

from __future__ import annotations

from typing import Any, Optional

from connectors.base import BaseConnector
from models.paper import Author, PaperMetadata


OPENALEX_BASE = "https://api.openalex.org"


class OpenAlexConnector(BaseConnector):
    """Search OpenAlex for scholarly works with OA PDF links."""

    name = "openalex"

    def __init__(self, api_key: Optional[str] = None, email: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key
        self._email = email

    def search(self, query: str, max_results: int = 50, year_from: int = 0) -> list[PaperMetadata]:
        params: dict[str, Any] = {
            "search": query,
            "per_page": min(max_results, 200),
            "filter": "has_abstract:true",
        }
        if year_from > 0:
            params["filter"] += f",publication_year:>={year_from}"
        if self._api_key:
            params["api_key"] = self._api_key
        if self._email:
            params["mailto"] = self._email

        data = self.http.get_json(f"{OPENALEX_BASE}/works", params=params)
        results_data = data.get("results", [])

        records: list[PaperMetadata] = []
        for w in results_data:
            doi_raw = w.get("doi") or w.get("id", "")
            doi = doi_raw.replace("https://doi.org/", "") if doi_raw else ""
            openalex_id = w.get("id", "").replace("https://openalex.org/", "")

            authors = [
                Author(
                    name=a.get("author", {}).get("display_name", ""),
                    orcid=a.get("author", {}).get("orcid"),
                    affiliation=(a.get("institutions", [{}])[0].get("display_name", "") if a.get("institutions") else ""),
                )
                for a in w.get("authorships", [])
            ]

            # Best OA PDF URL
            best_oa = w.get("best_oa_location") or {}
            pdf_url = best_oa.get("pdf_url") or ""

            # Keywords from concepts
            keywords = [c.get("display_name", "") for c in w.get("concepts", [])[:10]]

            abstract_text = ""
            if w.get("abstract_inverted_index"):
                abstract_text = _decode_inverted_index(w["abstract_inverted_index"])

            # Journal info
            primary_loc = w.get("primary_location") or {}
            source = primary_loc.get("source") or {}
            journal = source.get("display_name", "")
            journal_cites_per_year = source.get("cites_per_year", 0.0)

            # Citation count
            citation_count = w.get("cited_by_count", 0)

            records.append(
                PaperMetadata(
                    collection="",
                    paper_id="",
                    title=w.get("title") or w.get("display_name", ""),
                    authors=authors,
                    doi=doi if doi else None,
                    published=w.get("publication_date"),
                    abstract=abstract_text,
                    keywords=keywords,
                    source="openalex",
                    source_id=openalex_id,
                    pdf_url=pdf_url if pdf_url else None,
                    journal=journal,
                    citation_count=citation_count,
                    url=doi_raw or w.get("id", ""),
                    extra={"journal_cites_per_year": journal_cites_per_year},
                )
            )

        return records


def _decode_inverted_index(inverted: dict[str, list[int]]) -> str:
    """Rebuild abstract text from OpenAlex inverted index."""
    if not inverted:
        return ""
    position_word: dict[int, str] = {}
    for word, positions in inverted.items():
        for pos in positions:
            position_word[pos] = word
    return " ".join(position_word[i] for i in sorted(position_word))
