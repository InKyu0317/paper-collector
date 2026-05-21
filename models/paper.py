"""Pydantic models for scientific papers and their metadata.

Compatible with downstream consumption by Docling, Neo4j, ChromaDB,
LlamaIndex, and Graph RAG systems.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator, model_validator


class Author(BaseModel):
    """Represents a single paper author."""

    name: str = ""
    given_name: str = ""
    family_name: str = ""
    full_name: str = ""
    orcid: Optional[str] = None
    affiliation: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class PaperLink(BaseModel):
    """Describes a link to an external resource for a paper."""

    url: str
    content_type: str = ""
    relation: str = ""
    version: str = ""
    license_url: str = ""

    model_config = ConfigDict(extra="forbid")


class PaperMetadata(BaseModel):
    """Complete metadata record for a collected research paper.

    This is the canonical schema written to ``metadata.json`` inside
    every ``{paper_id}/`` folder.  All connectors map their source
    responses into this unified model.
    """

    paper_id: str = Field(default="", description="Stable, deterministic paper identifier (auto-generated)")
    collection: str = Field(..., description="Collection name (e.g. 'aluminosilicate')")
    title: str = Field(default="", description="Paper title")
    authors: list[Author] = Field(default_factory=list)
    doi: Optional[str] = Field(default=None, description="DOI in bare form")
    url: str = Field(default="", description="Canonical landing page URL")
    published: Optional[str] = Field(default=None, description="ISO 8601 publication date")
    abstract: str = Field(default="", description="Full abstract text")
    keywords: list[str] = Field(default_factory=list)
    source: str = Field(
        default="",
        description="Originating source identifier (arxiv, openalex, crossref, …)",
    )
    source_id: str = Field(
        default="",
        description="Source-specific identifier (arXiv id, OpenAlex W-id, …)",
    )
    pdf_path: str = Field(default="", description="Relative path to downloaded PDF file")
    pdf_url: Optional[str] = Field(default=None, description="URL used to download the PDF")
    pdf_accessible: bool = Field(
        default=False, description="Whether the PDF was successfully downloaded and verified"
    )
    links: list[PaperLink] = Field(
        default_factory=list,
        description="Additional resource links (OA versions, supplementary materials, …)",
    )
    license_info: str = Field(default="", description="License identified for the paper")
    is_open_access: bool = Field(default=False)
    oa_status: str = Field(default="")  # gold, green, hybrid, bronze, closed
    citation_count: int = Field(default=0)
    journal: str = Field(default="")
    publisher: str = Field(default="")
    added_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp when the paper was first collected",
    )
    updated_at: str = Field(
        default="",
        description="ISO 8601 UTC timestamp of last metadata update",
    )
    extra: dict[str, object] = Field(
        default_factory=dict,
        description="Extensible key-value store for source-specific fields "
        "(Neo4j properties, ChromaDB metadata, etc.)",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _auto_paper_id(self) -> PaperMetadata:
        if self.paper_id:
            return self
        self.paper_id = PaperMetadata.generate_paper_id(
            doi=self.doi or "",
            source=self.source or "",
            source_id=self.source_id or "",
        )
        return self

    @staticmethod
    def generate_paper_id(doi: str = "", source: str = "", source_id: str = "") -> str:
        """Derive a deterministic, collision-resistant paper identifier.

        Priority:  DOI > (source, source_id) > hash of title+source+source_id

        Returns a human-readable id prefixed by the source, e.g.
        ``arxiv_2101.12345`` or ``oa_W2741809807``.
        """
        if doi:
            # Normalise DOI: lowercase, strip whitespace, drop resolver prefix
            clean = doi.strip().lower()
            for prefix in ("https://doi.org/", "doi:", "doi.org/", "http://doi.org/"):
                clean = clean.removeprefix(prefix)
            # Sanitize for filesystem: replace invalid chars
            clean = clean.replace("/", "_").replace(":", "_").replace("\\", "_")
            clean = "".join(c for c in clean if c.isalnum() or c in "._-")
            return f"doi_{clean}"

        if source and source_id:
            sid = source_id.replace("/", "_").replace(":", "_").replace("\\", "_")
            sid = "".join(c for c in sid if c.isalnum() or c in "._-")
            return f"{source}_{sid}"

        # Last-resort fallback — sha1 of combined inputs
        digest = hashlib.sha1(
            f"{source}:{source_id}".encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:12]
        return f"hash_{digest}"


class CollectionSummary(BaseModel):
    """Lightweight summary of a collection's state."""

    name: str
    total_papers: int
    papers_with_pdf: int
    last_collected_at: str = ""
