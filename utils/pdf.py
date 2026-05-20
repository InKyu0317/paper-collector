"""PDF verification utilities.

Performs lightweight integrity checks on downloaded PDFs
without requiring a full PDF parsing dependency.
"""

from __future__ import annotations

from pathlib import Path


# Magic bytes at the start of every valid PDF
PDF_HEADER_MAGIC = b"%PDF-"


def verify_pdf(path: str | Path) -> bool:
    """Basic checks to confirm a file is a valid, non-corrupt PDF.

    Returns True if the file:
    - Exists and has nonzero size
    - Starts with ``%PDF-``
    - Is under 200 MB

    Returns False for anything that doesn't pass these checks.
    """
    try:
        p = Path(path)
        if not p.is_file():
            return False

        size = p.stat().st_size
        if size == 0:
            return False

        # Arbitrary sanity cap — real research papers are rarely > 200 MB
        if size > 200 * 1024 * 1024:
            return False

        with p.open("rb") as f:
            header = f.read(5)

        return header == PDF_HEADER_MAGIC

    except (OSError, IOError):
        return False


def verify_pdf_bytes(data: bytes) -> bool:
    """Same verification but operates on in-memory bytes."""
    if not data:
        return False
    if len(data) > 200 * 1024 * 1024:
        return False
    return data[:5] == PDF_HEADER_MAGIC
