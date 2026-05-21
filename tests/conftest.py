"""Shared test fixtures and configuration."""

import pytest
from pathlib import Path
import tempfile

from models.config import AppConfig
from models.paper import Author, PaperMetadata
from utils.storage import StorageManager


@pytest.fixture
def tmp_data_dir():
    """Provide a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def app_config(tmp_data_dir):
    """Return an AppConfig pointing to a temp data directory."""
    return AppConfig(
        data_dir=tmp_data_dir,
        download_pdfs=False,
    )


@pytest.fixture
def storage(tmp_data_dir):
    """Return a StorageManager backed by a temp directory."""
    return StorageManager(tmp_data_dir)


@pytest.fixture
def sample_paper():
    """Return a minimal PaperMetadata for testing."""
    return PaperMetadata(
        collection="test-collection",
        title="Test Paper Title",
        authors=[Author(name="Test Author")],
        doi="10.1234/test.2024.001",
        published="2024-01-15",
        abstract="This is a test abstract.",
        keywords=["test", "materials"],
        source="arxiv",
        source_id="2401.00001",
    )
