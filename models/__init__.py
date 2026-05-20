"""Data models for the paper collector system."""

from models.paper import Author, CollectionSummary, PaperMetadata
from models.collection import CollectionConfig, SearchQuery
from models.config import AppConfig, get_config, set_config

__all__ = [
    "Author",
    "CollectionConfig",
    "CollectionSummary",
    "PaperMetadata",
    "SearchQuery",
    "AppConfig",
    "get_config",
    "set_config",
]
