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

    # arXiv API politeness: cap per-run page size to a small batch.
    PAGE_SIZE = 5

    def __init__(
        self,
        delay_seconds: float = 3.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._delay = delay_seconds
        self._client = arxiv.Client(
            page_size=self.PAGE_SIZE,
            delay_seconds=delay_seconds,
            num_retries=10,
        )

    def search(
        self,
        query: str,
        max_results: int = 50,
        year_from: int = 0,
        page: int = 1,
        extra_filters: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> list[PaperMetadata]:
        # arXiv supports field-scoped filters inline via the query string.
        # See https://info.arxiv.org/help/api/user-manual.html#query_details
        #
        # IMPORTANT: do NOT re-wrap `query` in extra parentheses when appending
        # AND clauses. arXiv's query parser has been observed to reject nested
        # groups (HTTP 429 / empty results) for combined queries like
        # `(((a) AND (b)) AND cat:x)`. Since `cat:` and `submittedDate:` are
        # joined with AND, operator precedence is preserved without grouping.
        # If the caller passes a top-level OR query, they MUST parenthesise it
        # themselves (which the profile/preset builders already do).
        if extra_filters:
            cat = extra_filters.get("cat")
            if cat:
                query = f"{query} AND cat:{cat}"

        if year_from > 0:
            date_filter = f" AND submittedDate:[{year_from}01010000 TO 299912312359]"
            query = f"{query}{date_filter}"

        # Fetch up to (page * PAGE_SIZE) results so we can skip prior pages.
        # The arxiv library streams results; we still cap the *returned* size to
        # `max_results` (per-page batch) below.
        per_page = min(max_results, self.PAGE_SIZE)
        fetch_total = per_page * max(page, 1)
        search = arxiv.Search(
            query=query,
            max_results=fetch_total,
            sort_by=arxiv.SortCriterion.Relevance,
        )

        results: list[PaperMetadata] = []
        try:
            skip = (page - 1) * per_page
            count = 0
            for result in self._client.results(search):
                count += 1
                if count <= skip:
                    continue
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

                if len(results) >= per_page:
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
