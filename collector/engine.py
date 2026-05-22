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
from data.sjr import SJRLookup
from models.collection import CollectionConfig, SearchQuery
from models.config import AppConfig
from models.paper import PaperMetadata
from utils.http import HttpClient
from utils.logging import get_logger
from utils.pdf import verify_pdf_bytes
from utils.state import QueryState
from utils.storage import StorageManager

logger = get_logger(__name__)


class CollectionEngine:
    """Runs the full collect pipeline for a set of collections."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.storage = StorageManager(config.data_dir)
        self.query_state = QueryState(config.data_dir / ".state")
        self.sjr = SJRLookup(cache_dir=config.data_dir / ".sjr")

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

                # Resume from last saved page for incremental collection
                page = self.query_state.get_page(collection_cfg.name, sq.connector, sq.query)
                logger.info("search_page", connector=sq.connector, page=page)

                records = connector.search(
                    sq.query,
                    max_results=sq.max_results,
                    year_from=year_from,
                    page=page,
                    extra_filters=sq.extra_filters,
                )
                for r in records:
                    r.collection = collection_cfg.name
                all_records.extend(records)
                stats["searched"] += len(records)

                # Advance state only if we got results AND connector supports pagination
                if records and connector.supports_pagination:
                    self.query_state.advance_page(collection_cfg.name, sq.connector, sq.query, page + 1)

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
        """Filter papers by journal quality using SJR quartile data.

        Priority:
        1. SJR quartile (Q1/Q2/Q3/Q4) — authoritative from scimagojr.com
        2. Fallback: journal_cites_per_year (Q1 ≈ 50+)
        3. Fallback: citation_count threshold
        4. Fallback: journal_whitelist
        """
        quality_tier = self.config.quality_tier
        min_journal_cites_per_year = cfg.min_journal_cites_per_year
        min_paper_citation_count = cfg.min_paper_citation_count
        journal_whitelist = cfg.journal_whitelist

        # If nothing is configured, return all records
        if (quality_tier in ("all", "")
                and min_journal_cites_per_year <= 0
                and min_paper_citation_count <= 0
                and not journal_whitelist):
            return records

        filtered: list[PaperMetadata] = []
        sjr_used = 0
        cites_fallback_used = 0

        for r in records:
            # ── Primary: SJR Quartile filter ──
            if quality_tier and quality_tier not in ("all", ""):
                if r.issn and self.sjr.is_quartile(r.issn, quality_tier):
                    r.quartile = self.sjr.get_quartile(r.issn) or ""
                    sjr_used += 1
                elif r.issn:
                    # ISSN found but doesn't match tier — skip
                    logger.debug(
                        "filter_sjr_quartile",
                        paper_id=r.paper_id,
                        journal=r.journal,
                        issn=r.issn,
                        quartile=self.sjr.get_quartile(r.issn),
                        required=quality_tier,
                    )
                    continue
                else:
                    # No ISSN — typically arXiv preprints. By default drop them
                    # because a "Q1 only" filter is meaningless without journal info.
                    # Users can opt in via PAPER_COLLECTOR_ALLOW_PREPRINTS_IN_QUARTILE_FILTER=true.
                    if not self.config.allow_preprints_in_quartile_filter:
                        logger.debug(
                            "filter_no_issn_under_quartile",
                            paper_id=r.paper_id,
                            source=r.source,
                            required=quality_tier,
                        )
                        continue

            # ── Fallback: Journal whitelist check ──
            if journal_whitelist and r.journal not in journal_whitelist:
                continue

            # ── Fallback: Journal cites/year check (Q1 approximation) ──
            if min_journal_cites_per_year > 0 and not r.issn:
                journal_cpy = r.extra.get("journal_cites_per_year", 0.0)
                if journal_cpy < min_journal_cites_per_year:
                    logger.debug(
                        "filter_journal_cites",
                        paper_id=r.paper_id,
                        journal=r.journal,
                        cites_per_year=journal_cpy,
                        threshold=min_journal_cites_per_year,
                    )
                    continue
                cites_fallback_used += 1

            # ── Fallback: Paper citation count check ──
            if min_paper_citation_count > 0 and r.citation_count < min_paper_citation_count:
                logger.debug(
                    "filter_citation_count",
                    paper_id=r.paper_id,
                    citation_count=r.citation_count,
                    threshold=min_paper_citation_count,
                )
                continue

            filtered.append(r)

        removed = len(records) - len(filtered)
        logger.info(
            "quality_filter_done",
            input=len(records),
            kept=len(filtered),
            removed=removed,
            quality_tier=quality_tier,
            sjr_matched=sjr_used,
            cites_fallback=cites_fallback_used,
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
