"""CLI tool to view collected papers with quality metrics.

Usage:
    python workflows/view.py
    python workflows/view.py -c aluminosilicate
    python workflows/view.py --sort citations
    python workflows/view.py --format markdown
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from models.collection import DEFAULT_COLLECTIONS
from models.config import AppConfig
from models.paper import PaperMetadata
from utils.storage import StorageManager

console = Console()


def load_papers(collection: str, data_dir: Path) -> list[PaperMetadata]:
    """Load all paper metadata for a collection."""
    storage = StorageManager(data_dir)
    return storage.load_all_metadata(collection)


def format_table(papers: list[PaperMetadata], sort_by: str = "citations") -> Table:
    """Create a rich table from paper metadata."""
    table = Table(
        title="Collected Papers",
        show_header=True,
        header_style="bold magenta",
    )

    table.add_column("#", style="dim", width=4)
    table.add_column("Title", width=40)
    table.add_column("Journal", width=25)
    table.add_column("Citations", justify="right", width=10)
    table.add_column("Source", width=10)
    table.add_column("PDF", justify="center", width=5)
    table.add_column("URL", width=30)

    # Sort papers
    if sort_by == "citations":
        papers = sorted(papers, key=lambda p: p.citation_count, reverse=True)
    elif sort_by == "title":
        papers = sorted(papers, key=lambda p: p.title.lower())
    elif sort_by == "journal":
        papers = sorted(papers, key=lambda p: p.journal.lower())

    for i, p in enumerate(papers, 1):
        journal_cpy = p.extra.get("journal_cites_per_year", 0.0)
        journal_display = p.journal
        if journal_cpy > 0:
            journal_display = f"{p.journal} ({journal_cpy:.0f}/yr)"

        url_display = p.url[:35] + "..." if len(p.url) > 35 else p.url

        table.add_row(
            str(i),
            p.title[:50] + ("…" if len(p.title) > 50 else ""),
            journal_display[:30] + ("…" if len(journal_display) > 30 else ""),
            str(p.citation_count),
            p.source,
            "✓" if p.pdf_path else "—",
            url_display,
        )

    return table


def format_markdown(papers: list[PaperMetadata], sort_by: str = "citations") -> str:
    """Create markdown table from paper metadata."""
    if sort_by == "citations":
        papers = sorted(papers, key=lambda p: p.citation_count, reverse=True)
    elif sort_by == "title":
        papers = sorted(papers, key=lambda p: p.title.lower())
    elif sort_by == "journal":
        papers = sorted(papers, key=lambda p: p.journal.lower())

    lines = [
        "| # | Title | Journal | Citations | Source | PDF | URL |",
        "|---|-------|---------|-----------|--------|-----|-----|",
    ]

    for i, p in enumerate(papers, 1):
        journal_cpy = p.extra.get("journal_cites_per_year", 0.0)
        journal_display = p.journal
        if journal_cpy > 0:
            journal_display = f"{p.journal} ({journal_cpy:.0f}/yr)"

        title = p.title[:40].replace("|", "\\|") + ("…" if len(p.title) > 40 else "")
        journal = journal_display[:25].replace("|", "\\|")
        url = p.url[:30].replace("|", "\\|")

        lines.append(
            f"| {i} | {title} | {journal} | {p.citation_count} | {p.source} | {'✓' if p.pdf_path else '—'} | {url} |"
        )

    return "\n".join(lines)


@click.command()
@click.option("-c", "--collection", default=None, help="Collection name (default: all)")
@click.option("--sort", default="citations", type=click.Choice(["citations", "title", "journal"]), help="Sort order")
@click.option("--format", "fmt", default="table", type=click.Choice(["table", "markdown", "json"]), help="Output format")
@click.option("--min-citations", default=0, type=int, help="Filter by minimum citation count")
def main(collection, sort, fmt, min_citations):
    """View collected papers with quality metrics."""
    config = AppConfig()
    collections = [collection] if collection else list(DEFAULT_COLLECTIONS)

    all_papers: list[PaperMetadata] = []
    for name in collections:
        papers = load_papers(name, config.data_dir)
        if min_citations > 0:
            papers = [p for p in papers if p.citation_count >= min_citations]
        all_papers.extend(papers)

    if not all_papers:
        console.print("[yellow]No papers found.[/yellow]")
        return

    # Summary stats
    total = len(all_papers)
    with_pdf = sum(1 for p in all_papers if p.pdf_path)
    avg_citations = sum(p.citation_count for p in all_papers) / total if total else 0
    journals = set(p.journal for p in all_papers if p.journal)

    console.print(f"\n[bold]Collection Summary[/bold]")
    console.print(f"  Total papers: {total}")
    console.print(f"  With PDF: {with_pdf}")
    console.print(f"  Avg citations: {avg_citations:.1f}")
    console.print(f"  Unique journals: {len(journals)}")
    console.print()

    if fmt == "table":
        console.print(format_table(all_papers, sort))
    elif fmt == "markdown":
        console.print(format_markdown(all_papers, sort))
    elif fmt == "json":
        console.print(json.dumps([p.model_dump() for p in all_papers], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
