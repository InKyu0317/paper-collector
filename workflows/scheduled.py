"""Scheduled collection entry point — used by GitHub Actions.

Three modes, controlled by env inputs:

1. **Preset only** (`COLLECTIONS=...`, `KEYWORDS` empty):
   Run each preset's hand-crafted queries as-is.

2. **Keyword only** (`COLLECTIONS` empty, `KEYWORDS=...`):
   Create a standalone `custom-*` collection from keywords.

3. **Preset × Keyword intersection** (BOTH set):
   For each preset, run queries shaped as `(preset_topic) AND (keyword)`
   and store results into the preset's collection folder.
   This is the mode that answers "papers about <preset topic> that also
   mention <keyword>".
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
        all_results: list[dict] = []

        preset_names = config.collections_list
        # Forward env-driven knobs into the profile (previously ignored).
        profile = parse_keywords(
            config.keywords,
            quality_tier=config.quality_tier,
            years_back=config.years_back,
            max_results=config.default_max_results_per_query,
        )

        if preset_names and profile:
            # ── Mode 3: Preset × Keyword intersection ──
            logger.info(
                "running_intersection",
                presets=preset_names,
                keywords=profile.keywords,
                quality_tier=profile.quality_tier,
                years_back=profile.years_back,
            )
            for name in preset_names:
                preset = DEFAULT_COLLECTIONS.get(name)
                if preset is None:
                    logger.warning("unknown_preset", name=name)
                    continue
                collection = profile.build_intersected_collection(preset)
                logger.info(
                    "running_intersected_collection",
                    preset=name,
                    topic=preset.search_topic,
                    keywords=profile.keywords,
                    query_count=len(collection.queries),
                )
                result = engine.run_collection(collection)
                all_results.append(result)

        elif preset_names:
            # ── Mode 1: Preset only ──
            logger.info("running_presets", names=preset_names)
            results = engine.run_all(preset_names)
            all_results.extend(results)

        elif profile:
            # ── Mode 2: Keyword only (no preset) ──
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
            logger.warning(
                "nothing_to_do",
                hint="Set PAPER_COLLECTOR_COLLECTIONS and/or PAPER_COLLECTOR_KEYWORDS",
            )

        total_new = sum(r["new"] for r in all_results)
        total_errors = sum(r["errors"] for r in all_results)
        logger.info(
            "scheduled_run_complete",
            collections=len(all_results),
            new=total_new,
            errors=total_errors,
        )

        if total_errors > 0:
            raise SystemExit(1)
    finally:
        engine.close()


if __name__ == "__main__":
    run_scheduled()
