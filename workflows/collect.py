"""CLI entry point for interactive/manual collection runs.

Usage:
    python workflows/collect.py
    python workflows/collect.py --collection aluminosilicate
    python workflows/collect.py --keywords "plasma resistance"
    python workflows/collect.py -c aluminosilicate --keywords "plasma resistance"  # intersection
    python workflows/collect.py --dry-run
    python workflows/collect.py --no-pdf
"""

from __future__ import annotations

import sys

import click

from collector.engine import CollectionEngine
from models.collection import DEFAULT_COLLECTIONS, CollectionConfig
from models.config import AppConfig
from models.profile import parse_keywords
from utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


@click.command()
@click.option("-c", "--collection", multiple=True, help="Preset collection name(s) to process.")
@click.option("--keywords", default="", help="Comma-separated keywords. Combined with preset topic when --collection is also given.")
@click.option("--quality-tier", default="all", type=click.Choice(["all", "Q1", "Q2", "Q3", "Q4"]))
@click.option("--years-back", default=5, show_default=True, type=int)
@click.option("--dry-run", is_flag=True, help="Search only, do not save.")
@click.option("--no-pdf", is_flag=True, help="Skip PDF downloads.")
@click.option("--max-results", default=5, show_default=True, help="Max results per query.")
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def main(collection, keywords, quality_tier, years_back, dry_run, no_pdf, max_results, log_level):
    configure_logging(level=log_level, json_format=False)
    config = AppConfig()
    config.download_pdfs = not no_pdf
    config.quality_tier = quality_tier
    config.years_back = years_back

    preset_names = list(collection) if collection else list(DEFAULT_COLLECTIONS)
    profile = parse_keywords(
        keywords,
        quality_tier=quality_tier,
        years_back=years_back,
        max_results=max_results,
    )

    # Decide which collections to actually run.
    collections_to_run: list[CollectionConfig] = []

    if collection and profile:
        # Intersection mode: only the explicitly requested presets × keywords.
        for name in preset_names:
            preset = DEFAULT_COLLECTIONS.get(name)
            if preset is None:
                click.echo(f"  ? unknown preset: {name}")
                continue
            collections_to_run.append(profile.build_intersected_collection(preset))
    elif profile and not collection:
        # Keyword-only mode.
        collections_to_run.append(profile.build_collection())
    else:
        # Preset-only mode (default).
        for name in preset_names:
            preset = DEFAULT_COLLECTIONS.get(name)
            if preset is None:
                click.echo(f"  ? unknown preset: {name}")
                continue
            collections_to_run.append(preset)

    if dry_run:
        click.echo("DRY RUN - previewing queries:\n")
        for cfg in collections_to_run:
            click.echo(f"  [{cfg.display_name or cfg.name}]  (stored under: {cfg.name}/)")
            for sq in cfg.queries:
                filters = f"  filters={sq.extra_filters}" if sq.extra_filters else ""
                click.echo(f"    {sq.connector:10s} | {sq.query}{filters}")
            click.echo("")
        return

    engine = CollectionEngine(config)
    results: list[dict] = []
    try:
        for cfg in collections_to_run:
            results.append(engine.run_collection(cfg))
    finally:
        engine.close()

    total_new = sum(r["new"] for r in results)
    total_skipped = sum(r["skipped"] for r in results)
    total_errors = sum(r["errors"] for r in results)
    click.echo(f"\nDone. {total_new} new, {total_skipped} skipped, {total_errors} errors.")
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
