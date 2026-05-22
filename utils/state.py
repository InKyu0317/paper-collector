"""Persistent query state for incremental collection.

Tracks the last page/offset for each (collection, connector, query) tuple
so that daily runs resume where they left off instead of re-fetching page 1.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from utils.logging import get_logger

logger = get_logger(__name__)


def _query_hash(connector: str, query: str) -> str:
    return hashlib.md5(f"{connector}:{query}".encode()).hexdigest()[:12]


class QueryState:
    """Per-query pagination state persisted to disk."""

    def __init__(self, state_dir: Path):
        self._state_file = state_dir / "query_state.json"
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        try:
            self._state_file.write_text(json.dumps(self._data, indent=2))
        except OSError as e:
            logger.warning("state_save_failed", error=str(e))

    def get_page(self, collection: str, connector: str, query: str) -> int:
        key = f"{collection}:{_query_hash(connector, query)}"
        return self._data.get(key, {}).get("page", 1)

    def advance_page(self, collection: str, connector: str, query: str, new_page: int) -> None:
        key = f"{collection}:{_query_hash(connector, query)}"
        self._data[key] = {"page": new_page}
        self._save()

    def reset(self, collection: str, connector: str, query: str) -> None:
        key = f"{collection}:{_query_hash(connector, query)}"
        self._data.pop(key, None)
        self._save()
