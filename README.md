# Indie Census

[Read in English](README.md) · [Leer en español](README.es.md)

Open data observatory of the independent game development ecosystem.

---

> **Project Status:** Under active development. This is a personal project being built steadily and methodically, prioritizing software engineering robustness and analytical rigor over speed. Every module is built following Test-Driven Development (TDD), with hermetic test suites (no external network calls or uncontrolled randomness), strict typing, and immutable data contracts defined before implementation.

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

---

## MVP Definition (Minimum Viable Product)

The goal of the MVP (`v0.1.0`) is to build solid data engineering foundations and validate end-to-end technical and methodological feasibility with zero infrastructure cost:

- **Resilient and Reproducible Ingestion:** HTTP client with strict rate limits, exponential backoff with jitter on HTTP 429 status codes, and atomic checkpoints for fault-tolerant resumption.
- **Calibrated Control Sample:** An initial set of 100 representative Steam titles (balanced across engines and categories) locked via SHA-256 hash to audit classifier precision.
- **Data Lakehouse Architecture:**
  - **Bronze:** Immutable storage of partitioned raw payloads, secured by cryptographic integrity hashes.
  - **Silver:** Normalization, strict typing with Pydantic/Arrow, and automated quality contracts that reject anomalies.
  - **Gold:** Aggregated datasets ready for analytics and metric derivation.
- **Reproducible Delivery:** An initial clean and verifiable dataset in open formats (Parquet/CSV), backed by automated CI test suites.

---

## Engineering Principles

- **TDD Invariant:** No extraction, transformation, or quality module is implemented before its corresponding test suite is written.
- **Hermetic Testing:** Unit and integration tests never touch live networks; dependencies like clocks, sleep intervals, and random seeds are injected.
- **Immutability and Traceability:** Raw data is never overwritten; recomputations always branch from historical source truth.
- **Zero-Cost Design:** Fully automated and reproducible on lightweight infrastructure without recurring cloud server costs.
