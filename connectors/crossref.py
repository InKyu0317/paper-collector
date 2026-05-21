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

    def search(self, query: str, max_results: int = 50, year_from: int = 0) -> list[PaperMetadata]:
        filters = {"type": "journal-article"}
        if year_from > 0:
            filters["from-pub-date"] = f"{year_from}-01-01"

        all_items = []
        offset = 0
        page_size = min(max_results, 1000)

        while len(all_items) < max_results:
            remaining = max_results - len(all_items)
            limit = min(page_size, remaining)

            result = self._cr.works(
                query=query,
                filter=filters,
                limit=limit,
                offset=offset,
            )

            items = result.get("message", {}).get("items", [])
            if not items:
                break

            all_items.extend(items)
            offset += limit

            # Crossref caps total results at 10000; stop if we got fewer than requested
            if len(items) < limit:
                break

        records: list[PaperMetadata] = []
        for item in all_items[:max_results]:
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
                    citation_count=citation_count,
                    url=item.get("URL", ""),
                )
            )

        return records
