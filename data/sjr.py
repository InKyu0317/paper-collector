"""SCImago Journal Rank (SJR) data loader.

Downloads the official SJR ranking from scimagojr.com, parses the XLS file,
and builds an ISSN → Quartile (Q1/Q2/Q3/Q4) mapping for quality filtering.

Data source: https://www.scimagojr.com/journalrank.php
- XLS columns include: Rank, Sourceid, Title, Type, Issn, SJR, SJR Best Quartile, H index
- "SJR Best Quartile" column contains Q1, Q2, Q3, or Q4

Fallback: GitHub-hosted CSV (Michael-E-Rose/SCImagoJournalRankIndicators)
if scimagojr.com is unreachable.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Optional

from utils.logging import get_logger

logger = get_logger(__name__)

# Official SJR XLS download URL (updated annually by Scimago)
SJR_XLS_URL = "https://www.scimagojr.com/journalrank.php?year={year}&type=all&out=xls"

# Fallback: GitHub-hosted CSV (no quartile column, SJR-based heuristic)
SJR_CSV_URL = "https://raw.githubusercontent.com/Michael-E-Rose/SCImagoJournalRankIndicators/master/all.csv"

# Built-in fallback: well-known Q1 journals (ISSN → "Q1")
# Covers major materials science / chemistry / physics journals
BUILTIN_Q1_ISSNS = {
    # Nature family
    "0028-0836", "1476-4687",  # Nature
    "2058-8437",  # Nature Reviews Materials
    "2397-3366",  # npj Computational Materials
    "2397-3374",  # npj 2D Materials
    # Science family
    "0036-8075", "1095-9203",  # Science
    "2375-2548",  # Science Advances
    # Materials / Chemistry
    "0935-9648", "1521-4095",  # Advanced Materials
    "2198-3844",  # Advanced Energy Materials
    "1748-0124", "1748-0132",  # Nature Nanotechnology
    "1932-6203",  # PLOS ONE (broad, but high impact)
    "0002-7863", "1520-5126",  # JACS
    "1433-7851", "1521-3773",  # Angewandte Chemie
    "1745-2475", "1745-2483",  # Nature Physics
    "2468-5194",  # Matter
    "2666-3864",  # Cell Reports Physical Science
    # Electrochemistry / Energy
    "0378-7753",  # Journal of Power Sources
    "1359-4311",  # Applied Energy
    "0306-2619",  # Applied Energy (alt ISSN)
    # Ceramics / Materials
    "0955-2219",  # Journal of the European Ceramic Society
    "1359-6454", "1873-2453",  # Acta Materialia
    "0022-3093",  # Journal of Non-Crystalline Solids
    "0272-8842",  # Journal of the American Ceramic Society
    "1747-7786",  # Nature Reviews Physics
}


class SJRLookup:
    """ISSN → Quartile lookup table backed by SJR data."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self._cache_dir = cache_dir or Path("./collections/.sjr")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self._cache_dir / "sjr_quartiles.json"
        self._mapping: dict[str, str] = {}  # ISSN → "Q1"/"Q2"/"Q3"/"Q4"
        self._loaded = False

    @property
    def mapping(self) -> dict[str, str]:
        if not self._loaded:
            self.load()
        return self._mapping

    def load(self, force_refresh: bool = False) -> None:
        """Load SJR quartile mapping from cache, download, or fallback."""
        if self._loaded and not force_refresh:
            return

        # 1. Try cache
        if not force_refresh and self._cache_file.exists():
            try:
                data = json.loads(self._cache_file.read_text())
                self._mapping = data.get("issn_to_quartile", {})
                self._loaded = True
                logger.info(
                    "sjr_loaded_from_cache",
                    count=len(self._mapping),
                    year=data.get("year", "unknown"),
                )
                return
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("sjr_cache_corrupt", error=str(e))

        # 2. Try downloading official SJR XLS
        if self._try_download_xls():
            return

        # 3. Try fallback CSV (SJR-based heuristic for quartile)
        if self._try_download_csv():
            return

        # 4. Built-in fallback
        self._mapping = {issn: "Q1" for issn in BUILTIN_Q1_ISSNS}
        self._save_cache("builtin", len(self._mapping))
        logger.warning(
            "sjr_builtin_fallback",
            count=len(self._mapping),
            hint="Only well-known Q1 journals included. Download SJR data for full coverage.",
        )
        self._loaded = True

    def _try_download_xls(self) -> bool:
        """Download and parse official SJR XLS from scimagojr.com."""
        try:
            import datetime

            year = datetime.datetime.now().year - 1  # Previous year's data
            url = SJR_XLS_URL.format(year=year)

            import httpx

            resp = httpx.get(url, follow_redirects=True, timeout=30.0)
            if resp.status_code != 200:
                logger.warning("sjr_xls_download_failed", status=resp.status_code)
                return False

            # Parse XLS using xlrd (lightweight, no pandas needed)
            return self._parse_xls(resp.content, year)
        except ImportError:
            logger.debug("sjr_xlrd_not_available", hint="pip install xlrd")
            return False
        except Exception as e:
            logger.warning("sjr_xls_error", error=str(e))
            return False

    def _parse_xls(self, content: bytes, year: int) -> bool:
        """Parse SJR XLS content and build ISSN → quartile mapping."""
        try:
            import xlrd

            book = xlrd.open_workbook(file_contents=content)
            sheet = book.sheet_by_index(0)

            # Find column indices from header row
            header = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
            issn_idx = None
            quartile_idx = None
            for i, col in enumerate(header):
                col_lower = col.lower()
                if "issn" in col_lower:
                    issn_idx = i
                if "quartile" in col_lower:
                    quartile_idx = i

            if issn_idx is None or quartile_idx is None:
                logger.warning(
                    "sjr_xls_missing_columns",
                    header=header,
                    hint="Expected 'Issn' and 'SJR Best Quartile' columns",
                )
                return False

            mapping: dict[str, str] = {}
            for row_idx in range(1, sheet.nrows):
                issn_raw = str(sheet.cell_value(row_idx, issn_idx)).strip()
                quartile = str(sheet.cell_value(row_idx, quartile_idx)).strip().upper()
                if quartile not in ("Q1", "Q2", "Q3", "Q4"):
                    continue

                # Multiple ISSNs can be semicolon-separated
                for issn in issn_raw.split(";"):
                    issn = issn.strip()
                    if issn:
                        mapping[issn] = quartile

            self._mapping = mapping
            self._save_cache(f"scimagojr-{year}", len(mapping))
            logger.info("sjr_loaded_from_xls", count=len(mapping), year=year)
            self._loaded = True
            return True
        except Exception as e:
            logger.warning("sjr_xls_parse_error", error=str(e))
            return False

    def _try_download_csv(self) -> bool:
        """Download fallback CSV and estimate quartile from SJR score."""
        try:
            import httpx

            resp = httpx.get(SJR_CSV_URL, timeout=30.0)
            if resp.status_code != 200:
                return False

            # Parse CSV
            text = resp.text
            reader = csv.DictReader(io.StringIO(text))

            mapping: dict[str, str] = {}
            for row in reader:
                issn = row.get("Issn", "").strip()
                sjr_str = row.get("SJR", "").strip()
                if not issn or not sjr_str:
                    continue

                try:
                    sjr = float(sjr_str)
                except ValueError:
                    continue

                # Heuristic quartile based on SJR score
                # (approximate — official quartiles from XLS are more accurate)
                if sjr >= 3.0:
                    quartile = "Q1"
                elif sjr >= 1.5:
                    quartile = "Q2"
                elif sjr >= 0.5:
                    quartile = "Q3"
                else:
                    quartile = "Q4"

                for i in issn.split(";"):
                    i = i.strip()
                    if i:
                        mapping[i] = quartile

            self._mapping = mapping
            self._save_cache("github-csv-heuristic", len(mapping))
            logger.info("sjr_loaded_from_csv", count=len(mapping))
            self._loaded = True
            return True
        except Exception as e:
            logger.warning("sjr_csv_error", error=str(e))
            return False

    def _save_cache(self, source: str, count: int) -> None:
        """Save mapping to JSON cache."""
        import datetime

        data = {
            "source": source,
            "year": datetime.datetime.now().year,
            "count": count,
            "issn_to_quartile": self._mapping,
        }
        try:
            self._cache_file.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.warning("sjr_cache_save_failed", error=str(e))

    def get_quartile(self, issn: str) -> Optional[str]:
        """Get quartile for a given ISSN. Returns None if not found."""
        return self.mapping.get(issn.strip())

    def is_quartile(self, issn: str, tier: str) -> bool:
        """Check if a journal ISSN matches the given quality tier.

        Args:
            issn: Journal ISSN
            tier: "Q1", "Q2", "Q3", "Q4", or "all"

        Returns:
            True if the journal meets the tier requirement.
            "Q1" → only Q1 journals
            "Q2" → Q1 + Q2 journals
            "Q3" → Q1 + Q2 + Q3 journals
            "Q4" or "all" → all journals (always True)
        """
        if tier in ("all", "Q4"):
            return True

        q = self.get_quartile(issn)
        if q is None:
            # Unknown journal — include it (don't filter out unknowns)
            return True

        allowed = {
            "Q1": {"Q1"},
            "Q2": {"Q1", "Q2"},
            "Q3": {"Q1", "Q2", "Q3"},
        }
        return q in allowed.get(tier, {"Q1", "Q2", "Q3", "Q4"})

    def refresh(self) -> None:
        """Force refresh SJR data from source."""
        self._loaded = False
        self.load(force_refresh=True)
