"""Tests for PDF verification utilities."""

from utils.pdf import verify_pdf, verify_pdf_bytes


class TestVerifyPdfBytes:
    def test_valid_pdf_bytes(self):
        data = b"%PDF-1.4 some content"
        assert verify_pdf_bytes(data) is True

    def test_empty_bytes(self):
        assert verify_pdf_bytes(b"") is False

    def test_invalid_header(self):
        assert verify_pdf_bytes(b"NOTAPDF") is False

    def test_too_large(self):
        data = b"%PDF-" + b"x" * (200 * 1024 * 1024 + 1)
        assert verify_pdf_bytes(data) is False


class TestVerifyPdf:
    def test_valid_pdf_file(self, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 valid pdf")
        assert verify_pdf(pdf_file) is True

    def test_nonexistent_file(self, tmp_path):
        assert verify_pdf(tmp_path / "missing.pdf") is False

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.pdf"
        empty.touch()
        assert verify_pdf(empty) is False

    def test_invalid_header_file(self, tmp_path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"NOTAPDF")
        assert verify_pdf(bad) is False
