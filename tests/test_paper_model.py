"""Tests for PaperMetadata model."""

from models.paper import PaperMetadata, Author


class TestPaperMetadata:
    def test_generate_paper_id_from_doi(self):
        paper_id = PaperMetadata.generate_paper_id(
            doi="10.1234/test.2024.001"
        )
        assert paper_id.startswith("doi_")
        assert "10.1234" in paper_id

    def test_generate_paper_id_from_source(self):
        paper_id = PaperMetadata.generate_paper_id(
            source="arxiv", source_id="2401.00001"
        )
        assert paper_id == "arxiv_2401.00001"

    def test_generate_paper_id_fallback_hash(self):
        # source + source_id both present → returns "{source}_{source_id}"
        paper_id = PaperMetadata.generate_paper_id(
            source="unknown", source_id="xyz"
        )
        assert paper_id == "unknown_xyz"

        # Only source (no source_id) → fallback to hash
        paper_id_hash = PaperMetadata.generate_paper_id(
            source="onlysource", source_id=""
        )
        assert paper_id_hash.startswith("hash_")
        assert len(paper_id_hash) == 17  # "hash_" + 12 hex chars

    def test_auto_paper_id_on_construction(self, sample_paper):
        assert sample_paper.paper_id.startswith("doi_")

    def test_normalize_doi_removes_resolver_prefix(self):
        paper_id = PaperMetadata.generate_paper_id(
            doi="https://doi.org/10.1000/xyz"
        )
        assert "https://doi.org" not in paper_id

    def test_default_field_values(self):
        paper = PaperMetadata(
            collection="test",
            title="Test",
            source="arxiv",
            source_id="001",
        )
        assert paper.authors == []
        assert paper.keywords == []
        assert paper.pdf_path == ""
        assert paper.citation_count == 0
        assert paper.is_open_access is False
        assert paper.extra == {}
