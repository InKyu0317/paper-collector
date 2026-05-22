"""Scheduled collection entry point — used by GitHub Actions.

Supports two modes:
1. Preset collections (aluminosilicate, halide-solid-state-battery)
2. Dynamic keyword-based collections (user-provided keywords)

When keywords are provided, dynamic collections are created on the fly.
When no keywords, preset collections are used.
Both can run together.
"""

from __future__ import annotations

from collector.engine import CollectionEngine
from models.collection import DEFAULT_COLLECTIONS
from models.config import AppConfig
from models.profile import parse_keywords
from utils.logging import configure_logging, get_logger


def run_scheduled() -> None:
    configure_logging(level="INFO", json_format=True)
    logger = get_logger(__name__)

    config = AppConfig()
    engine = CollectionEngine(config)

    try:
        all_results = []

        # ── Mode 1: Preset collections ──
        preset_names = config.collections_list
        if preset_names:
            logger.info("running_presets", names=preset_names)
            results = engine.run_all(preset_names)
            all_results.extend(results)

        # ── Mode 2: Dynamic keyword collections ──
        keywords_str = config.keywords
        profile = parse_keywords(keywords_str)
        if profile:
            collection = profile.build_collection()
            logger.info(
                "running_keyword_collection",
                name=collection.name,
                keywords=profile.keywords,
                quality_tier=profile.quality_tier,
                years_back=profile.years_back,
            )
            result = engine.run_collection(collection)
            all_results.append(result)
        else:
            logger.info("no_keywords", hint="Set PAPER_COLLECTOR_KEYWORDS env var for dynamic search")

        total_new = sum(r["new"] for r in all_results)
        total_errors = sum(r["errors"] for r in all_results)
        logger.info("scheduled_run_complete", collections=len(all_results), new=total_new, errors=total_errors)

        if total_errors > 0:
            raise SystemExit(1)
    finally:
        engine.close()


if __name__ == "__main__":
    run_scheduled()
