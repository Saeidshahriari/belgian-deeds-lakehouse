# Code Ownership Guide

Use this as the interview walkthrough map. The goal is not to recite every line,
but to explain why every file exists and what risk it controls.

## Extraction Pipeline

`src/sagora_deeds/config.py`

Loads environment variables. `load_settings()` is for local extraction and
requires `GEMINI_API_KEY`. `load_database_url()` is separate so the API can start
without Gemini credentials.

`src/sagora_deeds/ocr.py`

Wraps OCRmyPDF. It creates a searchable PDF from scanned input and leaves the
original PDF untouched.

`src/sagora_deeds/extract.py`

Uses PyMuPDF for page counts, text-layer detection, and text extraction. It also
builds the Gemini prompt, calls Gemini with a JSON schema, retries transient API
errors, and validates the returned JSON.

`src/sagora_deeds/schemas.py`

Defines the Pydantic extraction contract. `GeminiExtraction` is what Gemini is
allowed to return. `DocumentExtraction` is the pipeline-owned artifact that adds
metadata such as `source_file`, `page_count`, `ocr_used`, and `source_type`.

`src/sagora_deeds/pipeline.py`

Orchestrates one PDF. It decides whether OCR is needed, extracts text, calls
Gemini, builds a validated `DocumentExtraction`, and writes the OCR/debug JSON
artifacts.

## Scripts

`scripts/run_one_pdf.py`

Stage 0 spike. It proves one PDF can go through the full vertical slice.

`scripts/run_three_pdfs.py`

Stage 1 proof. It checks the same pipeline across three different document
types.

`scripts/run_batch_pdfs.py`

Stage 3 batch runner. It processes the first N PDFs, reuses existing valid JSON
unless told to overwrite, and writes summary reports.

`scripts/analyze_extractions.py`

Turns the batch JSON files into data-quality numbers. This script justified the
database design instead of guessing table shape up front.

`scripts/load_extractions_to_db.py`

Stage 5 loader. It reads the batch summary, validates each extraction JSON,
computes a PDF SHA-256 hash for idempotency, and inserts documents, deeds,
companies, party roles, and extraction runs.

`scripts/query_db.py`

Small CLI for validating PostgreSQL contents before building the API.

`scripts/rebuild_batch_summary.py`

Maintenance helper that rebuilds summary counts from current extraction JSON
files.

`scripts/repair_extraction_metadata.py`

Maintenance helper from the schema-cleanup stage. It repairs deterministic
metadata in older JSON artifacts.

## Database

`src/sagora_deeds/db/models.py`

SQLAlchemy ORM schema. The key design decision is one source document can
contain multiple deeds, and each deed can contain multiple companies and party
roles.

`src/sagora_deeds/db/session.py`

Centralizes engine/session handling. Scripts can create one-off sessions, while
FastAPI initializes one singleton engine and reuses its connection pool.

`src/sagora_deeds/db/queries.py`

Shared query layer used by both CLI and API. This avoids duplicating SQL logic
across interfaces.

## API

`src/sagora_deeds/api/main.py`

FastAPI entrypoint. It exposes health, stats, company lookup, company mentions,
decision-makers, and company-name search.

`src/sagora_deeds/api/schemas.py`

Pydantic response models for HTTP output. These are separate from Gemini
schemas because API responses and LLM extraction contracts serve different
purposes.

## Docker and Migrations

`alembic/env.py`

Loads the project metadata and database URL so Alembic can run migrations.

`alembic/versions/0001_initial_schema.py`

Initial PostgreSQL schema migration.

`Dockerfile`

Builds the lightweight API image. It intentionally installs only API/database
dependencies, not OCR/Gemini dependencies.

`docker-compose.yml`

Runs PostgreSQL and the API. The API waits for the database healthcheck, applies
migrations, then starts Uvicorn.

## Key Decisions to Explain

- The pipeline was built before the database because OCR/Gemini extraction was
  the highest-risk part.
- `source_type`, `page_count`, and `ocr_used` are pipeline facts, not Gemini
  facts.
- `source_enterprise_number` comes from the dataset folder. It is provenance,
  not guaranteed extracted text.
- `extracted_enterprise_number` is only populated when the deed text itself
  states an enterprise number.
- Dates are text in v1 because OCR and multilingual date formats were unstable.
- `deed_type_normalized` exists but is null because normalization is a future
  cleanup step.
- `file_hash` makes database loading idempotent.
- The API is intentionally a thin wrapper over the same query functions used by
  the CLI.
