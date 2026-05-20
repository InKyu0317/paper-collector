"""Connector modules for scientific paper APIs."""

from connectors.arxiv import ArxivConnector
from connectors.base import BaseConnector, ConnectorRegistry
from connectors.crossref import CrossrefConnector
from connectors.openalex import OpenAlexConnector
from connectors.unpaywall import UnpaywallConnector

__all__ = [
    "ArxivConnector",
    "BaseConnector",
    "ConnectorRegistry",
    "CrossrefConnector",
    "OpenAlexConnector",
    "UnpaywallConnector",
]
