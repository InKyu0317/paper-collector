import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models.paper import PaperMetadata


class StorageManager:
    """Manages the on-disk storage layout for paper collections.

    The repository itself is the source of truth — no database dependency.
    Each paper lives in its own directory under
    ``collections/{collection_name}/papers/{paper_id}/``.

    Directory layout::

        collections/
          aluminosilicate/
            papers/
              arxiv_2101.12345/
                metadata.json
                paper.pdf
              oa_W2741809807/
                metadata.json
                paper.pdf
          halide-solid-state-battery/
            papers/
              ...
    """

    METADATA_FILENAME = "metadata.json"
    PDF_FILENAME = "paper.pdf"

    def __init__(self, data_dir: str | Path = "collections"):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ── Path helpers ────────────────────────────────────────────────

    def collection_dir(self, collection: str) -> Path:
        return self.data_dir / collection

    def papers_dir(self, collection: str) -> Path:
        return self.collection_dir(collection) / "papers"

    def paper_dir(self, collection: str, paper_id: str) -> Path:
        return self.papers_dir(collection) / paper_id

    def metadata_path(self, collection: str, paper_id: str) -> Path:
        return self.paper_dir(collection, paper_id) / self.METADATA_FILENAME

    def pdf_path(self, collection: str, paper_id: str) -> Path:
        return self.paper_dir(collection, paper_id) / self.PDF_FILENAME

    # ── Collection-level operations ──────────────────────────────────

    def ensure_collection(self, collection: str) -> Path:
        papers = self.papers_dir(collection)
        papers.mkdir(parents=True, exist_ok=True)
        return papers

    def list_collections(self) -> list[str]:
        if not self.data_dir.exists():
            return []
        return sorted(
            d.name
            for d in self.data_dir.iterdir()
            if d.is_dir()
        )

    # ── Paper presence checks ────────────────────────────────────────

    def paper_exists(self, collection: str, paper_id: str) -> bool:
        return self.metadata_path(collection, paper_id).exists()

    def pdf_exists(self, collection: str, paper_id: str) -> bool:
        path = self.pdf_path(collection, paper_id)
        return path.exists() and path.stat().st_size > 0

    def list_paper_ids(self, collection: str) -> list[str]:
        papers_dir = self.papers_dir(collection)
        if not papers_dir.exists():
            return []
        return sorted(
            d.name
            for d in papers_dir.iterdir()
            if d.is_dir() and (d / self.METADATA_FILENAME).exists()
        )

    def count_papers(self, collection: str) -> int:
        return len(self.list_paper_ids(collection))

    def count_pdfs(self, collection: str) -> int:
        return sum(
            1 for pid in self.list_paper_ids(collection)
            if self.pdf_exists(collection, pid)
        )

    # ── Metadata I/O ─────────────────────────────────────────────────

    def save_metadata(self, metadata: PaperMetadata) -> Path:
        self.ensure_collection(metadata.collection)
        paper_dir = self.paper_dir(metadata.collection, metadata.paper_id)
        paper_dir.mkdir(parents=True, exist_ok=True)

        metadata.pdf_path = str(
            self.pdf_path(metadata.collection, metadata.paper_id).relative_to(self.data_dir)
        )
        metadata.added_at = datetime.now(timezone.utc).isoformat()

        path = self.metadata_path(metadata.collection, metadata.paper_id)
        path.write_text(
            json.dumps(metadata.model_dump(), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return path

    def load_metadata(self, collection: str, paper_id: str) -> Optional[PaperMetadata]:
        path = self.metadata_path(collection, paper_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return PaperMetadata(**data)

    def load_all_metadata(self, collection: str) -> list[PaperMetadata]:
        records = []
        for paper_id in self.list_paper_ids(collection):
            md = self.load_metadata(collection, paper_id)
            if md is not None:
                records.append(md)
        return records

    # ── PDF I/O ──────────────────────────────────────────────────────

    def save_pdf(self, collection: str, paper_id: str, content: bytes) -> Path:
        self.ensure_collection(collection)
        paper_dir = self.paper_dir(collection, paper_id)
        paper_dir.mkdir(parents=True, exist_ok=True)

        path = self.pdf_path(collection, paper_id)
        path.write_bytes(content)
        return path

    def load_pdf(self, collection: str, paper_id: str) -> Optional[bytes]:
        path = self.pdf_path(collection, paper_id)
        if not path.exists():
            return None
        return path.read_bytes()
