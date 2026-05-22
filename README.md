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
# Run all preset collections
python workflows/collect.py

# Single preset collection
python workflows/collect.py -c aluminosilicate

# Keyword-only search (creates a custom-* collection)
python workflows/collect.py --keywords "topological insulator, spintronics"

# Preset x keyword INTERSECTION — papers about the preset's topic AND the keyword.
# Results are stored INTO the preset's existing folder (e.g. collections/aluminosilicate/).
python workflows/collect.py -c aluminosilicate --keywords "plasma resistance"

# Dry run (preview the actual queries that will be sent to each API)
python workflows/collect.py -c aluminosilicate --keywords "plasma resistance" --dry-run

# Quality tier + year range
python workflows/collect.py -c aluminosilicate --quality-tier Q1 --years-back 10

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

## Search Modes

The collector supports three modes, chosen automatically based on which inputs
are set (`PAPER_COLLECTOR_COLLECTIONS` and `PAPER_COLLECTOR_KEYWORDS`, or the
`-c` / `--keywords` CLI flags):

### 1. Preset only — `collection` set, no `keywords`

Runs each preset's hand-crafted queries verbatim. Stored under
`collections/<preset_name>/`.

```bash
python workflows/collect.py -c aluminosilicate
```

### 2. Keyword only — `keywords` set, no `collection`

Creates a standalone dynamic collection. Each keyword is searched in isolation
across all three connectors. Stored under `collections/custom-<keywords>/`.

```bash
python workflows/collect.py --keywords "topological insulator, spintronics"
```

### 3. Preset × Keyword **intersection** — both set

For each preset, the preset's `search_topic` is combined with every keyword
using each API's native AND syntax, and the results are stored **into the
preset's existing collection folder**. This is the mode that answers:

> "Give me papers about *<preset topic>* that *also* mention *<keyword>*."

```bash
python workflows/collect.py -c aluminosilicate --keywords "plasma resistance"
```

The actual queries sent to each API (visible via `--dry-run`):

| Connector | Combined query | Why this syntax |
|-----------|----------------|-----------------|
| arXiv | `(aluminosilicate) AND (plasma resistance)` | arXiv requires uppercase boolean operators |
| OpenAlex | `aluminosilicate AND plasma resistance` | OpenAlex `search` field supports explicit `AND` |
| Crossref | `aluminosilicate plasma resistance` | Crossref `query` is relevance-ranked; boolean operators are NOT supported and would be treated as literal tokens |

Papers are stored under `collections/aluminosilicate/papers/` — no separate
`custom-*` folder is created in this mode.

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
| **arXiv** | ✅ skip-based | 5 | Fetches `page × 5` results, skips prior pages, returns next 5 |
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
| **Request** | `arxiv.Search(query, max_results=page*5, sort_by=relevance)` then skip prior pages |
| **Category Filter** | `cat:<category>` appended to query (from `extra_filters["cat"]`) |
| **Year Filter** | `submittedDate:[YYYY01010000 TO 299912312359]` appended to query |
| **Rate Limit** | 3s delay, 10 retries |

**Example URL:**
```
https://export.arxiv.org/api/query?
  search_query=((aluminosilicate) AND (plasma resistance))
  AND cat:cond-mat.mtrl-sci
  AND submittedDate:[202101010000 TO 299912312359]
  &sortBy=relevance&sortOrder=descending&start=0&max_results=5
```

**Fields extracted:** title, authors (name, affiliation), doi, published, abstract, categories, pdf_url, arXiv ID

### OpenAlex (Scholarly Works)

| Item | Detail |
|------|--------|
| **API** | `https://api.openalex.org/works` |
| **Library** | `httpx` (direct HTTP) |
| **Request** | `GET ?search=...&per_page=5&filter=from_publication_date:YYYY-01-01` |
| **Pagination** | ❌ Not supported — always top 5 results |

**Example URL:**
```
https://api.openalex.org/works?
  search=aluminosilicate materials synthesis characterization
  &per_page=5
  &filter=from_publication_date:2021-01-01
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

Each preset declares a `search_topic` — the canonical noun phrase used when the
preset is combined with user-supplied keywords (intersection mode). The per-API
queries below are what runs in **preset-only** mode.

### aluminosilicate

**search_topic**: `aluminosilicate`

| Connector | Preset-only query | Extra filters | Daily |
|-----------|-------------------|---------------|-------|
| arXiv | `aluminosilicate` | `cat:cond-mat.mtrl-sci` | 5 |
| OpenAlex | `aluminosilicate materials synthesis characterization` | — | 5 |
| Crossref | `aluminosilicate zeolite geopolymer materials` | `type:journal-article` | 5 |

### halide-solid-state-battery

**search_topic**: `halide AND (solid-state battery OR solid electrolyte)`

| Connector | Preset-only query | Extra filters | Daily |
|-----------|-------------------|---------------|-------|
| arXiv | `halide AND (solid-state battery OR solid electrolyte)` | `cat:cond-mat.mtrl-sci` | 5 |
| OpenAlex | `halide solid electrolyte all-solid-state battery lithium` | — | 5 |
| Crossref | `halide solid state electrolyte battery lithium` | `type:journal-article` | 5 |

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
| `PAPER_COLLECTOR_ALLOW_PREPRINTS_IN_QUARTILE_FILTER` | When `quality_tier` is Q1-Q4, let papers without ISSN (e.g. arXiv preprints) bypass the SJR filter | `false` |
| `PAPER_COLLECTOR_LOG_LEVEL` | Log level | INFO |
| `PAPER_COLLECTOR_COLLECTIONS` | Preset collection name(s), comma-separated | `aluminosilicate,halide-solid-state-battery` |
| `PAPER_COLLECTOR_KEYWORDS` | Custom keywords, comma-separated. Combined with each preset's `search_topic` when `COLLECTIONS` is also set (intersection mode) | empty |
| `PAPER_COLLECTOR_YEARS_BACK` | Collect papers from the last N years (0 = all) | `5` |

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
| `collection` | *(empty)* | Run all presets (default) |
| | `aluminosilicate` | Run only aluminosilicate |
| | `halide-solid-state-battery` | Run only halide solid-state battery |
| `keywords` | *(empty)* | Preset-only mode |
| | `plasma resistance` | Combined with each selected preset's `search_topic` (intersection mode); results stored in the preset's folder |
| | `topological insulator, spintronics` | If `collection` is empty, creates standalone `custom-*` collections per keyword |
| `years` | `5` | Collect papers from the last N years (default: 5; 0 = no year filter) |
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
