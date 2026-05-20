"""Application-level configuration via environment variables and .env files.

Uses pydantic-settings for automatic loading and validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Top-level configuration for the Paper Collector application.

    All values are sourced from environment variables (or a ``.env`` file)
    with the prefix ``PAPER_COLLECTOR_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PAPER_COLLECTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Data directory ──────────────────────────────────────────────
    data_dir: Path = Path("./collections")
    """Root directory where all collection data is stored."""

    # ── arXiv ───────────────────────────────────────────────────────
    arxiv_delay_seconds: float = 3.0
    """Delay between arXiv API requests (politeness)."""

    # ── OpenAlex ────────────────────────────────────────────────────
    openalex_api_key: str = ""
    """API key from https://openalex.org/settings/api (optional but recommended)."""

    openalex_email: str = ""
    """Email for OpenAlex polite pool."""

    # ── Crossref ────────────────────────────────────────────────────
    crossref_email: str = ""
    """Email address for Crossref polite pool."""

    crossref_api_key: str = ""
    """Crossref Metadata Plus key (optional)."""

    # ── Unpaywall ───────────────────────────────────────────────────
    unpaywall_email: str = ""
    """Email address required for Unpaywall API access."""

    # ── HTTP ────────────────────────────────────────────────────────
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3
    http_retry_backoff: float = 1.0
    user_agent: str = "PaperCollector/0.1 (mailto:dev@example.com)"

    # ── PDF ─────────────────────────────────────────────────────────
    pdf_max_size_mb: float = 100.0
    """Maximum PDF file size to download (megabytes)."""

    pdf_download_timeout_seconds: float = 120.0

    # PDF size limit
    max_pdf_size_mb: int = 50

    # ── Collection defaults ─────────────────────────────────────────
    collections: list[str] = Field(
        default_factory=lambda: ["aluminosilicate", "halide-solid-state-battery"]
    )
    enabled_connectors: list[str] = Field(
        default_factory=lambda: ["arxiv", "openalex", "crossref", "unpaywall"]
    )
    download_pdfs: bool = True
    default_max_results_per_query: int = 50
    default_max_total_papers: int = 10_000

    # Http
    http_timeout_seconds: float = 30.0
    user_agent: str = "PaperCollector/0.1"

    # Rate limit
    rate_limit_rpm: int = 30

    # ── Logging ─────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"

    # ── Collections configuration path ──────────────────────────────
    collections_config_path: Optional[Path] = None
    """Optional path to a YAML/JSON file with collection definitions.
    When not set, collections are configured inline via the CLI."""

    # ── Derived helpers ─────────────────────────────────────────────

    @property
    def collections_root(self) -> Path:
        """Absolute path to the collections data directory."""
        return self.data_dir.resolve()

    def collection_dir(self, name: str) -> Path:
        """Return the path to a specific collection's root folder."""
        return self.collections_root / name

    def papers_dir(self, name: str) -> Path:
        """Return the path to the papers sub-folder for a collection."""
        return self.collection_dir(name) / "papers"


# Singleton convenience
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Return the singleton AppConfig, loading from env on first call."""
    global _config
    if _config is None:
        _config = AppConfig()  # type: ignore[call-arg]
    return _config


def set_config(config: AppConfig) -> None:
    """Override the singleton config (useful for testing)."""
    global _config
    _config = config
