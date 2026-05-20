"""Unpaywall API connector.

Checks open-access availability for papers by DOI.
Used as a PDF enrichment step after primary search connectors.
"""

from __future__ import annotations

from typing import Optional

from unpywall import Unpywall
from unpywall.utils import UnpywallCredentials

from connectors.base import BaseConnector
from models.paper import Author, PaperMetadata


class UnpaywallConnector(BaseConnector):
    """Enrich paper records with OA PDF locations via Unpaywall."""

    name = "unpaywall"

    def __init__(self, email: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        if email:
            UnpywallCredentials(email)

    def search(self, query: str, max_results: int = 50) -> list[PaperMetadata]:
        """Unpaywall is a DOI lookup service, not a search engine.

        Use `enrich()` instead for individual paper enrichment.
        Returns empty list — search is not supported.
        """
        return []

    def enrich(self, metadata: PaperMetadata) -> PaperMetadata:
        """Look up OA availability for a single paper by DOI.

        If an OA PDF is found, updates metadata.pdf_url.
        Returns the (possibly mutated) metadata object.
        """
        if not metadata.doi:
            return metadata

        try:
            result = Unpywall.doi(dois=[metadata.doi])
            data = result.get(metadata.doi, {})
        except Exception:
            return metadata

        if not data.get("is_oa"):
            return metadata

        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf") or best.get("url")
        if pdf_url and not metadata.pdf_url:
            metadata.pdf_url = pdf_url

        return metadata

    def enrich_batch(self, records: list[PaperMetadata]) -> list[PaperMetadata]:
        """Enrich multiple paper records with OA PDF URLs."""
        for record in records:
            self.enrich(record)
        return records
