"""Core collection engine.

Orchestrates the three-phase workflow:
1. Search — run queries across all enabled connectors
2. Enrich — resolve PDF availability via Unpaywall
3. Store — deduplicate, download PDFs, save metadata
"""

from __future__ import annotations

import time
from typing import Optional

from connectors.arxiv import ArxivConnector
from connectors.base import BaseConnector, ConnectorRegistry
from connectors.crossref import CrossrefConnector
from connectors.openalex import OpenAlexConnector
from connectors.unpaywall import UnpaywallConnector
from models.collection import CollectionConfig, SearchQuery
from models.config import AppConfig
from models.paper import PaperMetadata
from utils.http import HttpClient
from utils.logging import get_logger
from utils.pdf import verify_pdf_bytes
from utils.storage import StorageManager

logger = get_logger(__name__)


class CollectionEngine:
    """Runs the full collect pipeline for a set of collections."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.storage = StorageManager(config.data_dir)

        http = HttpClient(
            timeout=30.0,
            user_agent="PaperCollector/0.1",
            rate_limit_delay=1.0,
        )

        self.registry = self._build_registry(config, http)
        self._unpaywall: Optional[UnpaywallConnector] = None

    # ── Connector setup ─────────────────────────────────────────────

    def _build_registry(self, config: AppConfig, http: HttpClient) -> ConnectorRegistry:
        registry = ConnectorRegistry()
        enabled = set(config.enabled_connectors)

        if "arxiv" in enabled:
            registry.register(ArxivConnector(delay_seconds=config.arxiv_delay_seconds, http=http))
        if "openalex" in enabled:
            registry.register(OpenAlexConnector(api_key=config.openalex_api_key, http=http))
        if "crossref" in enabled:
            registry.register(CrossrefConnector(email=config.crossref_email, http=http))
        if "unpaywall" in enabled:
            self._unpaywall = UnpaywallConnector(email=config.unpaywall_email, http=http)
            registry.register(self._unpaywall)

        return registry

    # ── Collection-level orchestration ──────────────────────────────

    def run_collection(self, collection_cfg: CollectionConfig) -> dict:
        stats: dict = {
            "collection": collection_cfg.name,
            "searched": 0,
            "new": 0,
            "skipped": 0,
            "pdfs_downloaded": 0,
            "errors": 0,
        }
        logger.info("collection_start", name=collection_cfg.name)

        all_records: list[PaperMetadata] = []

        for sq in collection_cfg.queries:
            connector = self.registry.get(sq.connector)
            if connector is None:
                logger.warning(
                    "connector_not_found",
                    connector=sq.connector,
                    collection=collection_cfg.name,
                )
                continue

            try:
                logger.info(
                    "search_start",
                    connector=sq.connector,
                    query=sq.query[:80],
                )
                year_from = self.config.year_from or collection_cfg.year_from
                records = connector.search(sq.query, max_results=sq.max_results, year_from=year_from)
                for r in records:
                    r.collection = collection_cfg.name
                all_records.extend(records)
                stats["searched"] += len(records)
                logger.info(
                    "search_done",
                    connector=sq.connector,
                    found=len(records),
                )
            except Exception:
                logger.exception("search_failed", connector=sq.connector)
                stats["errors"] += 1

            time.sleep(1.0)

        # ── Enrich: resolve OA PDF availability via Unpaywall ────────
        all_records = self._enrich_with_unpaywall(all_records)

        # ── Filter: quality threshold (Q1 journals, citation count) ──
        all_records = self._filter_by_quality(all_records, collection_cfg)

        all_records = self._deduplicate(all_records)

        logger.info("deduplicated_total", count=len(all_records))

        for record in all_records:
            try:
                stored = self._store_paper(record)
                if stored:
                    stats["new"] += 1
                else:
                    stats["skipped"] += 1
            except Exception:
                logger.exception("store_failed", paper_id=record.paper_id)
                stats["errors"] += 1

        logger.info("collection_done", **stats)
        return stats

    # ── Enrichment ───────────────────────────────────────────────────

    def _enrich_with_unpaywall(self, records: list[PaperMetadata]) -> list[PaperMetadata]:
        """Enrich records with OA PDF URLs via Unpaywall DOI lookup.

        Only papers without an existing pdf_url are enriched.
        """
        if self._unpaywall is None:
            logger.debug("unpaywall_not_configured", hint="set UNPAYWALL_EMAIL to enable")
            return records

        to_enrich = [r for r in records if not r.pdf_url and r.doi]
        if not to_enrich:
            logger.info("enrich_skip", reason="all_records_have_pdf_urls")
            return records

        logger.info("enrich_start", count=len(to_enrich))
        enriched = self._unpaywall.enrich_batch(to_enrich)
        found = sum(1 for r in enriched if r.pdf_url)
        logger.info("enrich_done", total=len(to_enrich), oa_found=found)

        # Merge enriched records back
        enriched_map = {r.paper_id: r for r in enriched}
        result = []
        for r in records:
            if r.paper_id in enriched_map:
                result.append(enriched_map[r.paper_id])
            else:
                result.append(r)
        return result

    # ── Quality Filtering ────────────────────────────────────────────

    def _filter_by_quality(
        self, records: list[PaperMetadata], cfg: CollectionConfig
    ) -> list[PaperMetadata]:
        """Filter papers by journal quality (Q1 approximation) and citation count."""
        if cfg.min_journal_cites_per_year <= 0 and cfg.min_paper_citation_count <= 0 and not cfg.journal_whitelist:
            return records

        filtered: list[PaperMetadata] = []
        for r in records:
            # Journal whitelist check
            if cfg.journal_whitelist and r.journal not in cfg.journal_whitelist:
                continue

            # Journal cites/year check (Q1 approximation: typically 50+)
            journal_cpy = r.extra.get("journal_cites_per_year", 0.0)
            if cfg.min_journal_cites_per_year > 0 and journal_cpy < cfg.min_journal_cites_per_year:
                logger.debug(
                    "filter_journal_cites",
                    paper_id=r.paper_id,
                    journal=r.journal,
                    cites_per_year=journal_cpy,
                    threshold=cfg.min_journal_cites_per_year,
                )
                continue

            # Paper citation count check
            if cfg.min_paper_citation_count > 0 and r.citation_count < cfg.min_paper_citation_count:
                logger.debug(
                    "filter_citation_count",
                    paper_id=r.paper_id,
                    citation_count=r.citation_count,
                    threshold=cfg.min_paper_citation_count,
                )
                continue

            filtered.append(r)

        removed = len(records) - len(filtered)
        logger.info(
            "quality_filter_done",
            input=len(records),
            kept=len(filtered),
            removed=removed,
            min_journal_cpy=cfg.min_journal_cites_per_year,
            min_citations=cfg.min_paper_citation_count,
        )
        return filtered

    # ── Deduplication ───────────────────────────────────────────────

    def _deduplicate(self, records: list[PaperMetadata]) -> list[PaperMetadata]:
        seen: set[str] = set()
        unique: list[PaperMetadata] = []
        for r in records:
            rid = _record_key(r)
            if rid in seen:
                continue
            seen.add(rid)
            # Check on-disk
            if self.storage.paper_exists(r.collection, r.paper_id):
                continue
            unique.append(r)
        return unique

    # ── Store single paper ──────────────────────────────────────────

    def _store_paper(self, record: PaperMetadata) -> bool:
        pid = record.paper_id

        if self.storage.paper_exists(record.collection, pid):
            return False

        if self.config.download_pdfs and record.pdf_url:
            self._download_pdf(record)

        self.storage.save_metadata(record)
        return True

    # ── PDF download ────────────────────────────────────────────────

    def _download_pdf(self, record: PaperMetadata) -> None:
        connector = self.registry.get(record.source)
        if connector is None:
            return

        try:
            content = connector.resolve_pdf(record)
            if content and verify_pdf_bytes(content):
                max_bytes = self.config.max_pdf_size_mb * 1024 * 1024
                if len(content) <= max_bytes:
                    path = self.storage.save_pdf(
                        record.collection, record.paper_id, content
                    )
                    record.pdf_path = str(path.relative_to(self.config.data_dir.resolve()))
                    logger.info("pdf_downloaded", paper_id=record.paper_id, size=len(content))
        except Exception:
            logger.exception("pdf_failed", paper_id=record.paper_id)

    # ── Batch run ────────────────────────────────────────────────────

    def run_all(self, names: list[str]) -> list[dict]:
        from models.collection import DEFAULT_COLLECTIONS
        results: list[dict] = []
        for name in names:
            cfg = DEFAULT_COLLECTIONS.get(name)
            if cfg is None:
                logger.warning("unknown_collection", name=name)
                continue
            results.append(self.run_collection(cfg))
        return results

    # ── Lifecycle ───────────────────────────────────────────────────

    def close(self) -> None:
        for connector in self.registry:
            connector.close()


def _record_key(record: PaperMetadata) -> str:
    """Composite key for in-memory deduplication."""
    return f"{record.source}:{record.source_id}:{record.doi}"
