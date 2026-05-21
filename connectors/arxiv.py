"""arXiv API connector.

Uses the official arxiv Python wrapper for search and PDF download.
"""

from __future__ import annotations

import time
from typing import Optional

import arxiv

from connectors.base import BaseConnector
from models.paper import Author, PaperMetadata


class ArxivConnector(BaseConnector):
    """Search arXiv for preprints and download accessible PDFs."""

    name = "arxiv"

    def __init__(
        self,
        delay_seconds: float = 3.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._delay = delay_seconds
        self._client = arxiv.Client(
            page_size=200,
            delay_seconds=delay_seconds,
            num_retries=10,
        )

    def search(self, query: str, max_results: int = 50, year_from: int = 0, **kwargs) -> list[PaperMetadata]:
        # Add year filter to query if specified
        if year_from > 0:
            date_filter = f" AND submittedDate:[{year_from}01010000 TO 299912312359]"
            query = f"({query}){date_filter}"

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )

        results: list[PaperMetadata] = []
        try:
            for result in self._client.results(search):
                arxiv_id = result.entry_id.split("/")[-1]
                doi = result.doi or ""
                pdf_url = result.pdf_url or ""

                authors = [
                    Author(
                        name=a.name,
                        affiliation=", ".join(a.affiliation) if isinstance(a.affiliation, list) else (a.affiliation or ""),
                    )
                    for a in (result.authors or [])
                ]
                keywords = [cat if isinstance(cat, str) else cat.term for cat in (result.categories or [])]

                metadata = PaperMetadata(
                    collection="",
                    paper_id="",
                    title=result.title or "",
                    authors=authors,
                    doi=doi if doi else None,
                    published=result.published.isoformat() if result.published else None,
                    abstract=result.summary or "",
                    keywords=keywords,
                    source="arxiv",
                    source_id=arxiv_id,
                    pdf_url=pdf_url if pdf_url else None,
                    url=result.entry_id or "",
                )
                results.append(metadata)

                if len(results) >= max_results:
                    break
        except arxiv.HTTPError as e:
            from utils.logging import get_logger
            logger = get_logger(__name__)
            logger.warning("arxiv_rate_limited", status=e.status, url=str(e.url))

        return results

    def resolve_pdf(self, metadata: PaperMetadata) -> Optional[bytes]:
        if not metadata.pdf_url:
            return None
        time.sleep(self._delay)
        return self.http.download_bytes(metadata.pdf_url)
