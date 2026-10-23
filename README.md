# Indie Census

[Read in English](README.md) · [Leer en español](README.es.md)

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Tests](https://img.shields.io/badge/tests-383%20passed-brightgreen.svg)
![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)
![Architecture](https://img.shields.io/badge/architecture-Data%20Lakehouse-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Code Style](https://img.shields.io/badge/code%20style-ruff-000000.svg)

Open data observatory of the independent game development ecosystem.

> **Project Status:** Under active development (`v0.3.4`). This is a personal project being built steadily and methodically, prioritizing software engineering robustness and analytical rigor over speed. Every module is built following Test-Driven Development (TDD), with hermetic test suites (no external network calls or uncontrolled randomness), strict typing, and immutable data contracts defined before implementation.

## Overview and Focus Areas

Industry discussions around independent video games—such as engine adoption trends, store saturation, pricing distribution, and generative AI disclosures—are often driven by anecdotal opinions or commercial market reports with opaque methodologies.

Indie Census provides an open, reproducible, and verifiable data platform that turns empirical discussions into quantitative evidence. The observatory tracks five core areas:

1. **Game Engine Adoption:** Distribution and evolution of game technologies (open-source engines like Godot, commercial engines like Unity/Unreal, and custom frameworks) across the catalog.
2. **Pricing Dynamics:** Price points, release patterns, and commercial distribution across independent productions.
3. **Generative AI Disclosures:** Tracking declared AI usage in assets and code based on formal platform disclosure descriptors.
4. **Open Data and Reproducibility:** Publishing verified datasets and source pipelines so research findings can be reproduced and audited.
5. **Commercial Viability Modeling:** Multi-era Boxleiter sales and net revenue modeling, launch window competition density, and underserved niche detection.

## Architecture

The project implements a three-tier Data Lakehouse architecture with blocking quality contracts at each layer boundary:

- **Bronze Layer (`data/bronce/`):** Immutable raw storage partitioned by UTC date and resource type (`appdetails`, `appreviews`, `applist`), validated with SHA-256 cryptographic hashes.
- **Silver Layer (`data/plata/`):** Schema enforcement via Apache Arrow and Snappy-compressed Parquet, ISO-8601 normalization, HTML language table parsing, and semantic classification (`dim_game`, `game_review_summary`).
- **Gold Layer (`data/oro/`):** Star Schema dimensional modeling (`dim_game`, `dim_date`, `dim_genre_bridge`, `fact_game_performance`) exported to an analytical SQLite Data Mart (`data/oro/indie_census_mart.db`) with B-Tree indexes for BI integration.

### Release Roadmap

- **Phase 0 — Repository Governance & CI (`v0.0.0`):** Canonical directory hierarchy, `.gitignore` isolation, conventional commits pattern, and automated governance test suite.
- **Phase 1 — MVP Vertical Slice (`v0.1.0`):** Resilient HTTP client with rate-limiting and 429 quota backoff, transactional checkpoint manager, and calibrated 100-game control sample locked via SHA-256.
- **Phase 2 — Deterministic Classification & Semantics (`v0.2.0`):** Multi-tier engine classifier (evidence levels 1 to 4), multidimensional indie authenticity scoring algorithm with major publisher exclusion, formal generative AI disclosure classifier, and initial Gold Star Schema.
- **Phase 3 — Massive Ingestion & Boxleiter Modeling (`v0.3.0`):** Batch discovery via authenticated `IStoreService/GetAppList`, resilient console progress bar with dynamic ETA, and multi-era Boxleiter sales and net revenue modeling.
- **Phase 3 Extension — Distributed Sharding & Telemetry (`v0.3.1`):** Deterministic modular AppID sharding (`idx % N`) across distributed workers (Local PC and Google Colab Pro), master manifest locking, periodic tar.gz snapshot synchronization, and benchmark telemetry collector.
- **Phase 3 Extension — Zero-Gap Reconciliation & Forensic Audit (`v0.3.2` – `v0.3.4`):** Zero-gap snapshot merger, 100% catalog completeness audit against the master manifest, blocking Contract 10 verification, and consolidation of **63,770 titles (57,011 confirmed indies representing $7.120B USD in estimated net developer revenue)** in the Gold Data Mart (`data/oro/indie_census_mart.db`).
- **Phase 4 — Gold Analytical Mart, CI & Open Dataset (`v0.4.0`, upcoming):** Aggregated Gold master tables (engine penetration, price distribution, saturation indices), reviews re-extraction to eliminate language bias (`language=all`), secondary community tags enrichment, automated GitHub Actions workflows, and public dataset release (Parquet/CSV).
- **Phase 5 — Applied Data Science & Viability Modeling (`v0.5.0`):** Empirical sales and pricing regression models, launch window competition density metrics, and underserved tag gap detection.
- **Phase 6 — Headless Executive Reporting (`v1.0.0`):** Automated headless PDF/JSON audit report generation and decoupled analytical CLI.

## Engineering Standards

- **Strict TDD:** Every extraction, transformation, or quality module is backed by tests written prior to implementation (`test:` commit before `feat:` commit).
- **Hermetic Testing:** Unit and integration tests never make external network calls; dependencies like clocks, sleep intervals, and random seeds are injected or mocked.
- **Lakehouse Immutability:** Raw data is never overwritten; all recomputations branch deterministically from source truth in Bronze.
- **Local-First, Low-Cost Infrastructure:** Fully automated and reproducible on lightweight hardware without recurring cloud server dependencies.
- **Distributed Ingestion:** Modular sharding (`idx % total_workers == worker_id`) achieving 2.21x acceleration on cloud nodes and harvesting over 101,000 raw titles (see the [distributed extraction benchmark](benchmarks/comparativa_nodos_pc_vs_colab.md)).
- **Throughput and Rate Limiting:** Automatic exponential backoff with jitter and respect for `Retry-After` headers, safely managing over 34,000 HTTP 429 responses without pipeline interruption (see the [throughput benchmark](benchmarks/steam_api_throughput.md)).

## Environment Setup

```bash
# 1. Clone the repository
git clone https://github.com/Cesahz/indie-census.git
cd indie-census

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install pinned dependencies
pip install -r requirements.txt

# 4. Configure environment variables (optional for control sample, required for massive discovery)
cp .env.example .env
# Edit .env and set your STEAM_API_KEY
```

## Pipeline Execution

The pipeline orchestrator (`src/pipeline.py`) supports two execution modes:

### 1. Control Sample Workflow (100-Game Calibrated Set)

Executes extraction, transformation, and semantic quality contracts on the frozen control sample manifest:

```bash
python -m src.pipeline
```

### 2. Massive Catalog Workflow (Steam Catalog Scale)

Discovers, extracts, normalizes, and derives commercial revenue metrics for large-scale catalog subsets:

```bash
# Discover and ingest catalog titles, generating the SQLite Data Mart
python -m src.pipeline --modo masivo --descubrir --max-juegos 6000 --generar-oro

# Reprocess existing local Bronze partitions without network calls (63,770 titles)
python -m src.pipeline --modo masivo --omitir-extraccion --generar-oro --fecha 2026-10-18
```

### CLI Parameters Reference

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--modo` | `control \| masivo` | `control` | Execution mode (`control` uses the frozen manifest; `masivo` processes the wider Steam catalog). |
| `--descubrir` | Flag | `False` | Enables batch catalog discovery via authenticated `IStoreService/GetAppList`. |
| `--max-juegos` | Integer | `None` | Upper limit of titles to discover or process in massive mode. |
| `--generar-oro` | Flag | `False` | Generates the Gold Star Schema and analytical SQLite Data Mart (`data/oro/indie_census_mart.db`). |
| `--sin-progreso` | Flag | `False` | Disables the interactive console progress bar (recommended for CI/CD runs). |
| `--omitir-extraccion` | Flag | `False` | Skips network extraction and executes Silver/Gold transformations over existing Bronze partitions. |
| `--fecha` | `YYYY-MM-DD` | Current UTC | Temporal execution partition date. |
| `--ruta-base` | Directory path | `data/` | Base directory for Bronze, Silver, and Gold lakehouse layers. |
| `--manifiesto` | File path | `config/muestra_control.yaml` | Path to control sample YAML manifest. |

## Testing and Quality Verification

The test suite enforces full test coverage and hermetic boundaries:

```bash
# Run complete test suite (governance, extraction, transformation, classification, contracts)
pytest

# Run only governance and repository structure tests
pytest tests/gobernanza/

# Code style and linter verification
ruff check .
```

## License

This project is licensed under the terms of the [MIT License](LICENSE).
