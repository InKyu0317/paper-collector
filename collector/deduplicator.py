"""Deduplication logic for paper records.

Handles both in-memory (within a run) and on-disk (across runs)
duplicate detection.
"""

from __future__ import annotations

from typing import Optional

from models.paper import PaperMetadata
from utils.logging import get_logger
from utils.storage import StorageManager

logger = get_logger(__name__)


class Deduplicator:
    """Detects duplicate papers by source ID, DOI, and on-disk presence."""

    def __init__(self, storage: StorageManager):
        self._storage = storage
        self._seen: set[str] = set()

    def is_duplicate(self, record: PaperMetadata) -> bool:
        key = self._record_key(record)
        if key in self._seen:
            logger.debug("duplicate_in_memory", key=key)
            return True

        if self._storage.paper_exists(record.collection, record.paper_id):
            logger.debug("duplicate_on_disk", paper_id=record.paper_id)
            self._seen.add(key)
            return True

        self._seen.add(key)
        return False

    def deduplicate(self, records: list[PaperMetadata]) -> list[PaperMetadata]:
        unique: list[PaperMetadata] = []
        for r in records:
            if not self.is_duplicate(r):
                unique.append(r)
        logger.info(
            "dedup_result",
            input=len(records),
            unique=len(unique),
            duplicates=len(records) - len(unique),
        )
        return unique

    def reset(self) -> None:
        self._seen.clear()

    @staticmethod
    def _record_key(record: PaperMetadata) -> str:
        doi = record.doi or ""
        sid = record.source_id or ""
        src = record.source or ""
        return f"{src}:{sid}:{doi}"
