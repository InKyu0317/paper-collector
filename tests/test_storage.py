"""Tests for StorageManager."""

import json
from pathlib import Path


class TestStorageManager:
    def test_ensure_collection_creates_dir(self, storage):
        path = storage.ensure_collection("test")
        assert path.exists()
        assert path.is_dir()

    def test_paper_exists_false_initially(self, storage):
        assert storage.paper_exists("test", "nonexistent") is False

    def test_save_and_load_metadata(self, storage, sample_paper):
        saved_path = storage.save_metadata(sample_paper)
        assert saved_path.exists()

        loaded = storage.load_metadata("test-collection", sample_paper.paper_id)
        assert loaded is not None
        assert loaded.title == sample_paper.title
        assert loaded.doi == sample_paper.doi

    def test_save_and_load_pdf(self, storage, sample_paper):
        pdf_content = b"%PDF-1.4 test pdf content"
        storage.save_pdf("test-collection", sample_paper.paper_id, pdf_content)
        assert storage.pdf_exists("test-collection", sample_paper.paper_id)

        loaded = storage.load_pdf("test-collection", sample_paper.paper_id)
        assert loaded == pdf_content

    def test_list_paper_ids(self, storage, sample_paper):
        storage.save_metadata(sample_paper)
        ids = storage.list_paper_ids("test-collection")
        assert sample_paper.paper_id in ids

    def test_count_papers(self, storage, sample_paper):
        storage.save_metadata(sample_paper)
        assert storage.count_papers("test-collection") == 1

    def test_metadata_is_valid_json(self, storage, sample_paper):
        storage.save_metadata(sample_paper)
        metadata_path = storage.metadata_path("test-collection", sample_paper.paper_id)
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert "title" in data
        assert "authors" in data
