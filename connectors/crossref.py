"""Crossref API connector.

Uses the habanero library for DOI metadata lookup and search.
"""

from __future__ import annotations

from typing import Optional

from habanero import Crossref

from connectors.base import BaseConnector
from models.paper import Author, PaperMetadata


class CrossrefConnector(BaseConnector):
    """Search Crossref for journal articles with metadata and citation data."""

    name = "crossref"

    def __init__(self, email: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._cr = Crossref(mailto=email) if email else Crossref()

    def search(
        self,
        query: str,
        max_results: int = 50,
        year_from: int = 0,
        page: int = 1,
        extra_filters: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> list[PaperMetadata]:
        # Default to journal-article; caller can override via extra_filters["type"].
        filters: dict[str, str] = {"type": "journal-article"}
        if year_from > 0:
            filters["from-pub-date"] = f"{year_from}-01-01"
        if extra_filters:
            # Crossref habanero accepts hyphenated filter keys (e.g. from-pub-date).
            # The user passes e.g. {"type": "journal-article"} — apply directly.
            filters.update(extra_filters)

        # Safe batch size per run
        limit = min(max_results, 5)
        offset = (page - 1) * limit

        result = self._cr.works(
            query=query,
            filter=filters,
            limit=limit,
            offset=offset,
        )

        items = result.get("message", {}).get("items", [])
        records: list[PaperMetadata] = []
        for item in items:
            doi = item.get("DOI", "")
            title = (item.get("title") or [""])[0]

            authors = [
                Author(
                    name=f"{a.get('given', '')} {a.get('family', '')}".strip(),
                    orcid=a.get("ORCID", ""),
                    affiliation=(a.get("affiliation", [{}])[0].get("name", "") if a.get("affiliation") else ""),
                )
                for a in item.get("author", [])
            ]

            published_parts = item.get("published-print", {}).get("date-parts", [[]])[0]
            published = "-".join(str(p) for p in published_parts) if published_parts else None

            pdf_url = ""
            for link in item.get("link", []):
                if link.get("content-type") == "application/pdf":
                    pdf_url = link.get("URL", "")
                    break

            keywords = item.get("subject", [])
            journal = (item.get("container-title") or [""])[0]
            citation_count = item.get("is-referenced-by-count", 0)

            # ISSN extraction
            issn_obj = item.get("ISSN", [])
            issn = issn_obj[0] if isinstance(issn_obj, list) and issn_obj else ""

            records.append(
                PaperMetadata(
                    collection="",
                    paper_id="",
                    title=title,
                    authors=authors,
                    doi=doi,
                    published=published,
                    abstract=item.get("abstract", ""),
                    keywords=keywords,
                    source="crossref",
                    source_id=doi,
                    pdf_url=pdf_url if pdf_url else None,
                    journal=journal,
                    issn=issn,
                    citation_count=citation_count,
                    url=item.get("URL", ""),
                )
            )

        return records
