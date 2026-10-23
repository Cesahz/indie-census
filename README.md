# Indie Census

[Read in English](README.md) · [Leer en español](README.es.md)

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Tests](https://img.shields.io/badge/tests-383%20passed-brightgreen.svg)
![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)
![Architecture](https://img.shields.io/badge/architecture-Data%20Lakehouse-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Code Style](https://img.shields.io/badge/code%20style-ruff-000000.svg)

Open data observatory of the independent game development ecosystem.

---

> **Project Status:** Under active development (`v0.3.4`). This is a personal project being built steadily and methodically, prioritizing software engineering robustness and analytical rigor over speed. Every module is built following Test-Driven Development (TDD), with hermetic test suites (no external network calls or uncontrolled randomness), strict typing, and immutable data contracts defined before implementation.

---

## Intent and Vision

This observatory started as a personal initiative with the goal of giving back and providing open data value to the game development community, analysts, and researchers.

Debates surrounding the indie gaming landscape—such as game engine adoption, store saturation, pricing dynamics, and emerging technologies—are often dominated by anecdotal impressions, heated forum discussions, or commercial reports that do not disclose raw data or reproducible methodologies.

**Indie Census** aims to provide the community with an **open, citable, and methodologically auditable source** that turns empirical speculation into transparent, quantitative evidence.

The project does not aim to validate any single bias or focus exclusively on a single tool. Instead, it measures broader industry movements with neutrality:

1. **Game Engine Adoption and Shifts:** How development technologies (open-source engines, commercial engines, and custom frameworks) evolve and distribute across the indie catalog.
2. **Pricing Dynamics and Commercial Sustainability:** Price points, launch patterns, and economic survival among small-scale productions.
3. **Generative AI Disclosures:** Quantitative tracking and analysis of declared generative AI usage in assets and code, based on public platform disclosure policies.
4. **Open Data and Methodology:** Publishing not just graphs or conclusions, but clean datasets and pipeline source code so anyone in the community can reproduce or audit every finding.
5. **Commercial Viability Audit & Applied Data Science:** Transitioning from descriptive observation to a prescriptive and predictive diagnostic engine. Providing indie developers, publishers, and consultants with empirical sales/pricing regression scoring, launch window competition density analysis, saturated vs. underserved tag gap detection, and automated headless audit report generation (PDF/JSON).

---

## Architecture and Project Evolution

The platform follows a three-tier Data Lakehouse architecture (Bronze, Silver, Gold) with strict data contracts blocking anomalies at every boundary:

- **Bronze Layer (`data/bronce/`):** Immutable raw storage partitioned by UTC date and resource type (`appdetails`, `appreviews`, `applist`), guaranteed by cryptographic hash verification.
- **Silver Layer (`data/plata/`):** Normalization, type enforcement via Apache Arrow/Parquet, and automated quality contracts (`dim_game`, `game_review_summary`).
- **Gold Layer (`data/oro/`):** Star Schema dimensional modeling (`dim_game`, `dim_engine`, `fact_game_performance`) exported directly to an analytical SQLite Data Mart (`data/oro/indie_census_mart.db`) for BI consumption (Power BI, DuckDB, Metabase).

### Milestones and Releases

- **Phase 0 — Repository Governance & CI (`v0.0.0`):** Canonical directory hierarchy, strict `.gitignore` isolation, conventional commits pattern, and automated governance test suite.
- **Phase 1 — MVP Vertical Slice (`v0.1.0`):** Resilient HTTP client with backoff and 429 quota management, fault-tolerant checkpoint manager, and calibrated 100-game control sample locked via SHA-256.
- **Phase 2 — Deterministic Classification & Semantic Enrichment (`v0.2.0`):** Multi-tier game engine classifier (evidence levels 1-4), multi-dimensional indie authenticity scoring algorithm with major publisher exclusion, formal generative AI disclosure classifier, and initial Gold Star Schema.
- **Phase 3 — Massive Ingestion & Boxleiter Commercial Metrics (`v0.3.0`):** Batch discovery via authenticated `IStoreService/GetAppList`, resilient console progress bar with dynamic ETA, multi-era Boxleiter sales and net revenue modeling, and data cleansing for delisted items.
- **Phase 3 Extension — Distributed Multi-Node Sharding & Telemetry (`v0.3.1`):** Deterministic modular AppID sharding across distributed workers (Local PC and Google Colab Pro), immutable master manifest freezing, periodic tar.gz snapshot synchronization, and per-node telemetry benchmark collector.
- **Phase 3 Extension — Zero-Gap Reconciliation & Pre-Silver Audit (`v0.3.2`):** Zero-gap atomic snapshot merger, 100% catalog completeness audit against master manifest with residual fallback sweep, blocking Contract 10 pre-Silver verification, and consolidation of **63,770 titles (57,011 confirmed indies representing $7.120B USD net developer revenue and $15.197B USD total)** in the Gold Data Mart (`data/oro/indie_census_mart.db`).
- **Phase 4 — Gold Analytical Mart, CI Automation & Open Dataset (`v0.4.0`, upcoming):** Aggregated Gold master tables (engine penetration, price distribution, saturation indices), secondary community tags enrichment to unlock Level 2 engine classification, automated GitHub Actions Cron execution, public open dataset release (Parquet/CSV with `metodologia.md`, `diccionario_datos.md`, `limitaciones.md`), and the Strategic Control Milestone (12.1.1).
- **Phase 5 — Applied Data Science & Predictive Commercial Viability Core (`v0.5.0`):** Empirical sales and pricing regression models, launch window competition density metrics, and underserved niche gap detection.
- **Phase 6 — Headless Executive Audit Reporter & Diagnostic Microservice (`v1.0.0`):** Automated headless PDF/JSON audit report generation and decoupled diagnostic service.

---

## Engineering Principles

- **TDD Invariant:** No extraction, transformation, or quality module is implemented before its corresponding test suite is written and failing (`test:` commit before `feat:` commit).
- **Hermetic Testing:** Unit and integration tests never touch live networks; dependencies like clocks, sleep intervals, and random seeds are injected.
- **Immutability and Traceability:** Raw data is never overwritten; recomputations always branch from historical source truth.
- **Zero-Cost Design:** Fully automated and reproducible on lightweight infrastructure without recurring cloud server costs.
- **Distributed Multi-Node Ingestion:** Deterministic modular sharding (`idx % total_workers == worker_id`) achieving a 2.21x acceleration on cloud nodes and harvesting over 101,000 raw titles with zero server costs (see the [distributed extraction benchmark report](benchmarks/comparativa_nodos_pc_vs_colab.md)).
- **Ingestion Efficiency:** Quota and throughput optimization via batch authenticated endpoints (99.4% reduction in cataloging time and 188x acceleration over anonymous endpoints; see the [technical throughput benchmark](benchmarks/steam_api_throughput.md)).

---

## Environment Setup

```bash
# 1. Clone the repository
git clone https://github.com/Cesahz/indie-census.git
cd indie-census

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install pinned dependencies
pip install -r requirements.txt

# 4. Configure environment variables (optional for control sample, required for massive discovery)
cp .env.example .env
# Edit .env and set your STEAM_API_KEY
```

---

## Pipeline Execution

The pipeline orchestrator (`src/pipeline.py`) supports two primary execution workflows:

### 1. Control Sample Workflow (100-Game Calibrated Set)

Executes extraction, transformation, and semantic quality contracts on the frozen control sample manifest:

```bash
python -m src.pipeline
```

### 2. Massive Catalog Workflow (Full Catalog Scale)

Discovers, extracts, normalizes, and derives commercial revenue metrics for large-scale catalog subsets:

```bash
# Discover and ingest catalog titles, generating the SQLite Data Mart
python -m src.pipeline --modo masivo --descubrir --max-juegos 6000 --generar-oro

# Reprocess existing local Bronze partitions without network calls (63,770 titles)
python -m src.pipeline --modo masivo --omitir-extraccion --generar-oro --fecha 2026-10-18
```

### CLI Options Reference

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--modo` | `control \| masivo` | `control` | Execution mode (`control` uses the frozen manifest; `masivo` processes the wider Steam catalog). |
| `--descubrir` | Flag | `False` | Enables dynamic batch catalog discovery via authenticated `IStoreService/GetAppList`. |
| `--max-juegos` | Integer | `None` | Upper limit of games to discover or process in massive mode. |
| `--generar-oro` | Flag | `False` | Generates the Gold Star Schema and analytical SQLite Data Mart (`data/oro/indie_census_mart.db`). |
| `--sin-progreso` | Flag | `False` | Disables the interactive console progress bar (recommended for non-interactive CI/CD runs). |
| `--omitir-extraccion` | Flag | `False` | Skips network extraction and executes Silver/Gold transformations over existing Bronze partitions. |
| `--fecha` | `YYYY-MM-DD` | Current UTC | Temporal execution partition date. |
| `--ruta-base` | Directory path | `data/` | Base directory for Bronze, Silver, and Gold lakehouse layers. |
| `--manifiesto` | File path | `config/muestra_control.yaml` | Path to control sample YAML manifest. |

---

## Testing and Quality Verification

The test suite enforces complete coverage and hermetic boundaries:

```bash
# Run all automated tests (governance, extraction, transformation, classification, contracts)
pytest

# Run only governance and repository structure tests
pytest tests/gobernanza/

# Code style and linter verification
ruff check .
```

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).


