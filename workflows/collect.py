"""CLI entry point for interactive/manual collection runs.

Usage:
    python workflows/collect.py
    python workflows/collect.py --collection aluminosilicate
    python workflows/collect.py --dry-run
    python workflows/collect.py --no-pdf
"""

from __future__ import annotations

import sys

import click

from collector.engine import CollectionEngine
from models.collection import DEFAULT_COLLECTIONS
from models.config import AppConfig
from utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


@click.command()
@click.option("-c", "--collection", multiple=True, help="Collection name(s) to process.")
@click.option("--dry-run", is_flag=True, help="Search only, do not save.")
@click.option("--no-pdf", is_flag=True, help="Skip PDF downloads.")
@click.option("--max-results", default=100, show_default=True, help="Max results per query.")
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def main(collection, dry_run, no_pdf, max_results, log_level):
    configure_logging(level=log_level, json_format=False)
    config = AppConfig()
    config.download_pdfs = not no_pdf

    names = list(collection) if collection else list(DEFAULT_COLLECTIONS)

    if dry_run:
        click.echo("DRY RUN — previewing queries:\n")
        for name in names:
            cfg = DEFAULT_COLLECTIONS.get(name)
            if cfg is None:
                click.echo(f"  ? unknown: {name}")
                continue
            click.echo(f"  [{cfg.display_name}]")
            for sq in cfg.queries:
                sq.max_results = max_results
                click.echo(f"    {sq.connector:10s} | {sq.query}")
        return

    engine = CollectionEngine(config)
    results = engine.run_all(names)
    engine.close()

    total_new = sum(r["new"] for r in results)
    total_skipped = sum(r["skipped"] for r in results)
    total_errors = sum(r["errors"] for r in results)
    click.echo(f"\nDone. {total_new} new, {total_skipped} skipped, {total_errors} errors.")
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
