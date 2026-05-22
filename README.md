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
├── utils/             # Storage, HTTP, PDF, logging, state
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

# View collected papers
python workflows/view.py
python workflows/view.py -c aluminosilicate --sort citations
python workflows/view.py --format markdown
python workflows/view.py --min-citations 50
```

## Collection Pipeline

```
Search (3 connectors × 5 papers)
  → Unpaywall Enrichment (OA PDF resolution)
  → Quality Filtering (optional)
  → Deduplication (skip existing)
  → Store (metadata.json + PDF)
```

### Incremental Collection

매일 5개씩 안전하게 수집하여 점진적으로 데이터베이스를 쌓습니다:

| Connector | Pagination | Daily | Strategy |
|-----------|-----------|-------|----------|
| **arXiv** | ✅ skip-based | 5 | Previous pages skipped, next page fetched |
| **OpenAlex** | ❌ not supported | 5 | Always top 5; dedup skips existing, new papers bubble up |
| **Crossref** | ✅ offset-based | 5 | Offset advances by 5 each run |

**Daily total**: 6 queries × 5 = **max 30 papers** (actual less after dedup)

State is persisted in `collections/.state/query_state.json` and survives across GitHub Actions runs.

## Data Sources & API Requests

### arXiv (Preprints)

| Item | Detail |
|------|--------|
| **API** | `https://export.arxiv.org/api/query` |
| **Library** | `arxiv` (official wrapper) |
| **Request** | `arxiv.Search(query, max_results=5, sort_by=relevance)` |
| **Year Filter** | `submittedDate:[202101010000 TO 299912312359]` appended to query |
| **Rate Limit** | 3s delay, 10 retries |

**Example URL:**
```
https://export.arxiv.org/api/query?
  search_query=(aluminosilicate OR aluminosilicate materials synthesis)
  AND submittedDate:[202101010000 TO 299912312359]
  &sortBy=relevance&sortOrder=descending&start=0&max_results=100
```

**Fields extracted:** title, authors (name, affiliation), doi, published, abstract, categories, pdf_url, arXiv ID

### OpenAlex (Scholarly Works)

| Item | Detail |
|------|--------|
| **API** | `https://api.openalex.org/works` |
| **Library** | `httpx` (direct HTTP) |
| **Request** | `GET ?search=...&per_page=5&filter=publication_year:>=2021` |
| **Pagination** | ❌ Not supported — always top 5 results |

**Example URL:**
```
https://api.openalex.org/works?
  search=aluminosilicate materials synthesis characterization
  &per_page=5
  &filter=publication_year:>=2021
```

**Fields extracted:** title, authors (name, institution, ORCID), doi, publication_date, abstract (inverted index decoded), concepts/keywords, journal name, ISSN, cites_per_year, cited_by_count, best_oa_location.pdf_url, OpenAlex W-ID

### Crossref (DOI Metadata + Citations)

| Item | Detail |
|------|--------|
| **API** | Crossref REST API |
| **Library** | `habanero` |
| **Request** | `works(query, filter, limit=5, offset=...)` |
| **Pagination** | ✅ offset-based (page 1 → offset=0, page 2 → offset=5) |

**Fields extracted:** title, authors (given+family, affiliation, ORCID), DOI, ISSN, published-print date, abstract, subject/keywords, container-title (journal), is-referenced-by-count (citations), PDF link, URL

### Unpaywall (OA PDF Enrichment)

| Item | Detail |
|------|--------|
| **Role** | Post-search enrichment — resolves OA PDF URLs by DOI |
| **API** | `https://api.unpaywall.org/v2/{doi}` |
| **Library** | `unpywall` |
| **Target** | Only papers without existing `pdf_url` |

**Fields extracted:** is_oa, best_oa_location.url_for_pdf, best_oa_location.url

## Storage

The filesystem is the source of truth:

```
collections/
├── .state/
│   └── query_state.json          # Pagination state per query
├── aluminosilicate/
│   └── papers/
│       ├── arxiv_2301.07046v1/
│       │   ├── metadata.json
│       │   └── paper.pdf
│       ├── doi_10.1016_j.mtla.2024.102148/
│       │   ├── metadata.json
│       │   └── paper.pdf
│       └── ...
└── halide-solid-state-battery/
    └── papers/
        └── ...
```

### Metadata Schema (`metadata.json`)

```json
{
  "paper_id": "arxiv_2301.07046v1",
  "collection": "aluminosilicate",
  "title": "Synthesis of aluminosilicate...",
  "authors": [
    {"name": "John Doe", "affiliation": "MIT", "orcid": "0000-..."}
  ],
  "doi": "10.xxxx/xxxxx",
  "url": "https://arxiv.org/abs/2301.07046",
  "published": "2023-01-17",
  "abstract": "Full abstract text...",
  "keywords": ["cond-mat.mtrl-sci"],
  "source": "arxiv",
  "source_id": "2301.07046v1",
  "pdf_url": "https://arxiv.org/pdf/2301.07046.pdf",
  "pdf_path": "aluminosilicate/papers/arxiv_2301.07046v1/paper.pdf",
  "pdf_accessible": true,
  "citation_count": 5,
  "journal": "Nature Materials",
  "issn": "1476-4687",
  "quartile": "Q1",
  "is_open_access": true,
  "oa_status": "green",
  "license_info": "CC-BY-4.0",
  "added_at": "2026-05-22T01:50:50.215547+00:00",
  "updated_at": "",
  "extra": {"journal_cites_per_year": 62.5}
}
```

**Paper ID generation** (deterministic, collision-resistant):
1. DOI → `doi_{sanitized_doi}`
2. Source + source_id → `{source}_{sanitized_id}`
3. Fallback → `hash_{sha1}`

## Configured Collections

### aluminosilicate

| Connector | Query | Daily |
|-----------|-------|-------|
| arXiv | `aluminosilicate OR aluminosilicate materials synthesis` | 5 |
| OpenAlex | `aluminosilicate materials synthesis characterization` | 5 |
| Crossref | `aluminosilicate zeolite geopolymer materials` | 5 |

### halide-solid-state-battery

| Connector | Query | Daily |
|-----------|-------|-------|
| arXiv | `halide solid state battery OR halide electrolyte all solid state battery` | 5 |
| OpenAlex | `halide solid electrolyte all-solid-state battery lithium` | 5 |
| Crossref | `halide solid state electrolyte battery lithium` | 5 |

## Quality Filtering (SJR-Based Q1/Q2/Q3/Q4)

The system uses **SCImago Journal Rank (SJR)** data for accurate journal quality filtering.
SJR data is downloaded automatically from scimagojr.com on first run and cached locally.

### How It Works

```
1. Download SJR XLS from scimagojr.com (annual update)
   → Parse "SJR Best Quartile" column (Q1/Q2/Q3/Q4)
   → Cache as JSON at collections/.sjr/sjr_quartiles.json

2. Extract ISSN from each paper (OpenAlex/Crossref)

3. Match ISSN → Quartile
   → Q1: keep only Q1 journals
   → Q2: keep Q1 + Q2 journals
   → Q3: keep Q1 + Q2 + Q3 journals
   → all: no filtering
```

### Fallback Chain

If SJR data is unavailable:
1. **GitHub CSV** (Michael-E-Rose/SCImagoJournalRankIndicators) — SJR score → heuristic quartile
2. **Built-in list** — ~30 well-known Q1 journals (Nature, Science, Advanced Materials, etc.)

### Setting Quality Tier

**GitHub Actions** (recommended):
```
Actions → Scheduled Paper Collection → Run workflow
  quality_tier: Q1   ← select from dropdown
```

**Environment variable**:
```bash
PAPER_COLLECTOR_QUALITY_TIER=Q1
```

**CLI**:
```bash
python workflows/collect.py --quality-tier Q1
```

### Quartile Definitions

| Tier | Meaning | SJR Source |
|------|---------|------------|
| **Q1** | Top 25% journals in category | `SJR Best Quartile` from scimagojr.com |
| **Q2** | Top 50% journals | Same |
| **Q3** | Top 75% journals | Same |
| **Q4** | All journals (no filter) | Same |
| **all** | No filtering (default) | — |

### Legacy Filters (Still Available)

For papers without ISSN (e.g., arXiv preprints), legacy filters still apply:

| Filter | Description | Default |
|--------|-------------|---------|
| `min_journal_cites_per_year` | Minimum journal cites/year (Q1 ≈ 50+) | 0 (disabled) |
| `min_paper_citation_count` | Minimum paper citation count | 0 (disabled) |
| `journal_whitelist` | Only accept papers from specific journals | — |

Enable in `models/collection.py`:
```python
# In ALUMINOSILICATE_CONFIG or HALIDE_BATTERY_CONFIG:
min_journal_cites_per_year=50.0,
min_paper_citation_count=10,
```

## Configuration

All settings via environment variables (or `.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `PAPER_COLLECTOR_DATA_DIR` | Root data directory | `./collections` |
| `PAPER_COLLECTOR_ARXIV_DELAY_SECONDS` | arXiv politeness delay | 3.0 |
| `PAPER_COLLECTOR_OPENALEX_API_KEY` | OpenAlex API key | — |
| `PAPER_COLLECTOR_CROSSREF_EMAIL` | Crossref email | — |
| `PAPER_COLLECTOR_UNPAYWALL_EMAIL` | Unpaywall email | — |
| `PAPER_COLLECTOR_QUALITY_TIER` | Journal quality tier (all/Q1/Q2/Q3/Q4) | `all` |
| `PAPER_COLLECTOR_LOG_LEVEL` | Log level | INFO |
| `PAPER_COLLECTOR_COLLECTIONS` | Collections to process | all |

## CI/CD

GitHub Actions runs paper collection automatically and supports manual triggers.

### Schedule

| Trigger | Frequency | Time (UTC) | Time (KST) |
|---------|-----------|------------|------------|
| `cron` | Daily | 02:00 | 11:00 |

### Manual Run

Go to **Actions → Scheduled Paper Collection → Run workflow**.

| Input | Value | Description |
|-------|-------|-------------|
| `collection` | *(empty)* | Run all collections (default) |
| | `aluminosilicate` | Run only aluminosilicate |
| | `halide-solid-state-battery` | Run only halide solid-state battery |
| `years` | `5` | Collect papers from the last N years (default: 5) |
| `quality_tier` | `all` | Journal quality tier: all, Q1, Q2, Q3, Q4 |

On success, collected papers are automatically committed and pushed to `main`.

## Future Compatibility

Built for downstream integration with:

- **Docling** — document parsing
- **Neo4j** — graph knowledge base
- **ChromaDB** — vector store
- **LlamaIndex** — RAG pipelines
- **Graph RAG** — knowledge graph + retrieval

## License

MIT
