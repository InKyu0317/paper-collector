"""Persistent query state for incremental collection.

Tracks the last page/offset for each (collection, connector, query) tuple
so that daily runs resume where they left off instead of re-fetching page 1.

Each collection gets its own state file (query_state_<name>.json) so that
concurrent GitHub Actions runs for different collections never conflict.
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
    """Per-collection, per-query pagination state persisted to disk.

    Each collection name maps to a separate JSON file so that concurrent
    workflow runs (e.g. aluminosilicate vs halide) never touch the same file.
    """

    def __init__(self, state_dir: Path):
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
        # Lazy-loaded per-collection state dicts
        self._stores: dict[str, dict] = {}

    def _state_file(self, collection: str) -> Path:
        return self._state_dir / f"query_state_{collection}.json"

    def _get_store(self, collection: str) -> dict:
        if collection not in self._stores:
            path = self._state_file(collection)
            if path.exists():
                try:
                    self._stores[collection] = json.loads(path.read_text())
                except (json.JSONDecodeError, OSError):
                    self._stores[collection] = {}
            else:
                self._stores[collection] = {}
        return self._stores[collection]

    def _save(self, collection: str) -> None:
        path = self._state_file(collection)
        try:
            path.write_text(json.dumps(self._stores[collection], indent=2))
        except OSError as e:
            logger.warning("state_save_failed", collection=collection, error=str(e))

    def get_page(self, collection: str, connector: str, query: str) -> int:
        store = self._get_store(collection)
        key = f"{collection}:{_query_hash(connector, query)}"
        return store.get(key, {}).get("page", 1)

    def advance_page(self, collection: str, connector: str, query: str, new_page: int) -> None:
        store = self._get_store(collection)
        key = f"{collection}:{_query_hash(connector, query)}"
        store[key] = {"page": new_page}
        self._save(collection)

    def reset(self, collection: str, connector: str, query: str) -> None:
        store = self._get_store(collection)
        key = f"{collection}:{_query_hash(connector, query)}"
        store.pop(key, None)
        self._save(collection)
