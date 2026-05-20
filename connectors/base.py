"""Abstract base class and registry for paper source connectors.

Every connector implements:
- search(query, max_results) → list[PaperMetadata]
- resolve_pdf(metadata) → bytes | None
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from models.paper import PaperMetadata
from utils.http import HttpClient


class BaseConnector(ABC):
    """Abstract connector for a scientific paper data source."""

    name: str = "base"

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient()

    @abstractmethod
    def search(self, query: str, max_results: int = 50) -> list[PaperMetadata]:
        """Execute a search query and return normalized PaperMetadata records."""

    def resolve_pdf(self, metadata: PaperMetadata) -> bytes | None:
        """Attempt to download the PDF for a given paper.

        Returns raw bytes if successful, None otherwise.
        Default implementation uses metadata.pdf_url.
        """
        if not metadata.pdf_url:
            return None
        try:
            return self.http.download_bytes(metadata.pdf_url)
        except Exception:
            return None

    def close(self) -> None:
        self.http.close()


class ConnectorRegistry:
    """Registry of available connectors, keyed by name.

    Supports future extensibility — new connectors (Springer, Elsevier,
    Semantic Scholar, ACS) register here without modifying core logic.
    """

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        self._connectors[connector.name] = connector

    def get(self, name: str) -> BaseConnector | None:
        return self._connectors.get(name)

    def list_names(self) -> list[str]:
        return sorted(self._connectors.keys())

    def __iter__(self):
        return iter(self._connectors.values())
