"""Scheduled collection entry point — used by GitHub Actions."""

from __future__ import annotations

from collector.engine import CollectionEngine
from models.collection import DEFAULT_COLLECTIONS
from models.config import AppConfig
from utils.logging import configure_logging, get_logger


def run_scheduled() -> None:
    configure_logging(level="INFO", json_format=True)
    logger = get_logger(__name__)

    config = AppConfig()
    engine = CollectionEngine(config)

    try:
        results = engine.run_all(config.collections)
        total_new = sum(r["new"] for r in results)
        total_errors = sum(r["errors"] for r in results)
        logger.info("scheduled_run_complete", collections=len(results), new=total_new, errors=total_errors)

        if total_errors > 0:
            raise SystemExit(1)
    finally:
        engine.close()


if __name__ == "__main__":
    run_scheduled()
