# Paper Collector

Scientific paper collection system for materials science research.

Two collections: **aluminosilicate** and **halide-solid-state-battery**.

Designed for future Graph RAG and scientific agent workflows.

## Architecture

```
paper-collector/
├── collector/         # Collection engine + deduplication
├── connectors/        # API connectors (arXiv, OpenAlex, Crossref, Unpaywall)
├── models/            # Pydantic data models
├── utils/             # Storage, HTTP, PDF, logging
├── workflows/         # CLI + scheduled entry points
└── .github/workflows/ # CI/CD schedule
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

## Usage

```bash
# Run all collections
python workflows/collect.py

# Single collection
python workflows/collect.py -c aluminosilicate

# Dry run (preview queries)
python workflows/collect.py --dry-run

# Metadata only, skip PDFs
python workflows/collect.py --no-pdf

# Scheduled mode (GitHub Actions)
python workflows/scheduled.py
```

## Data Sources

| Source | Coverage | Auth | Python Lib |
|--------|----------|------|------------|
| arXiv | Preprints (cond-mat) | None | `arxiv` |
| OpenAlex | Comprehensive scholarly works | API key | `pyalex` |
| Crossref | DOI metadata + citations | Email (polite) | `habanero` |
| Unpaywall | OA PDF availability | Email | `unpywall` |

## Storage

The filesystem is the source of truth:

```
collections/
├── aluminosilicate/
│   └── papers/
│       ├── arxiv_2101.12345/
│       │   ├── metadata.json
│       │   └── paper.pdf
│       └── ...
└── halide-solid-state-battery/
    └── papers/
        └── ...
```

## Future Compatibility

Built for downstream integration with:

- **Docling** — document parsing
- **Neo4j** — graph knowledge base
- **ChromaDB** — vector store
- **LlamaIndex** — RAG pipelines
- **Graph RAG** — knowledge graph + retrieval

## Configuration

All settings via environment variables (or `.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `PAPER_COLLECTOR_DATA_DIR` | Root data directory | `./collections` |
| `PAPER_COLLECTOR_ARXIV_DELAY_SECONDS` | arXiv politeness delay | 3.0 |
| `PAPER_COLLECTOR_OPENALEX_API_KEY` | OpenAlex API key | — |
| `PAPER_COLLECTOR_CROSSREF_EMAIL` | Crossref email | — |
| `PAPER_COLLECTOR_UNPAYWALL_EMAIL` | Unpaywall email | — |
| `PAPER_COLLECTOR_LOG_LEVEL` | Log level | INFO |
| `PAPER_COLLECTOR_COLLECTIONS` | Collections to process | all |

## License

MIT
