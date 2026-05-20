"""Core collection engine that orchestrates all connectors."""

from collector.engine import CollectionEngine
from collector.deduplicator import Deduplicator

__all__ = [
    "CollectionEngine",
    "Deduplicator",
]
