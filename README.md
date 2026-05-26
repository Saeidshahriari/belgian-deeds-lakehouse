# Sagora Deeds

Risk-first data engineering pipeline for Belgian Gazette deed PDFs.

This project ingests deed PDFs from `data/`, runs OCR where needed, asks Gemini
for structured extraction, validates the result with Pydantic, stores validated
records in PostgreSQL, and exposes queryable data through FastAPI.

This is not a credit-risk model. It is the structured company/deed/party-role
data foundation a later agent workflow could use for credit-risk analysis,
decision-maker lookup, and peer comparison.

## 1. Plan & Scoping

### What I Tackled

I followed a risk-first build order:

1. One real PDF through OCR/text extraction, Gemini JSON, and Pydantic validation.
2. Three PDFs across different layouts to test whether the same prompt/schema held up.
3. A 50-PDF batch to measure OCR success, extraction success, validation failures, and data shape.
4. Database design after seeing real extracted JSON.
5. PostgreSQL persistence with SQLAlchemy, Alembic, and idempotent loading.
6. FastAPI endpoints over the loaded PostgreSQL data.
7. Docker Compose for PostgreSQL plus the API.

This order was deliberate. The highest-risk part of the challenge was not
FastAPI or Docker; it was whether scanned Belgian Gazette PDFs could be turned
into useful structured records. I therefore proved OCR plus Gemini plus Pydantic
before designing tables or endpoints.

### What I Skipped

- I did not process all 4,200 PDFs. I processed a 50-PDF batch because the brief
  values clarity of approach over maximum volume.
- I did not build a credit-risk model. The available data is foundational legal
  deed data, not financial risk data.
- I did not normalize all deed types yet. Raw values such as `CONSTITUTION`,
  `Constitution`, `Oprichting`, and `OPRICHTING` are stored, and the database has
  `deed_type_normalized` reserved for future cleanup.
- I did not Dockerize OCR/Gemini extraction. The final Docker stack serves
  PostgreSQL data through FastAPI; extraction remains a local script workflow.

### Stack Choices

- `OCRmyPDF` and Tesseract for scanned PDFs.
- `PyMuPDF` for PDF text detection and text extraction.
- `google-genai` with Gemini `2.5 Flash` for structured extraction.
- `Pydantic` for validation and JSON schema generation.
- `PostgreSQL` because the final design uses `JSONB`, `TIMESTAMPTZ`, indexes,
  and relational joins.
- `SQLAlchemy 2.x` and `Alembic` for models and migrations.
- `FastAPI` for a small HTTP wrapper with OpenAPI docs.
- Docker Compose for the final PostgreSQL plus API stack.

### Schema Choices

The schema is based on the first 50 processed PDFs:

```text
documents: 50
deeds: 168
companies: 181
party_roles: 574
```

The most important finding was that one PDF is not one company and not one deed.
In the 50-PDF batch, 49 PDFs contained multiple deed notices. Therefore the
database separates:

- `documents`: source PDF metadata, OCR state, file hash, source file path.
- `deeds`: one row per Gazette notice/deed extracted from a document.
- `companies`: one row per company mention inside a deed.
- `party_roles`: founders, directors, notaries, signatories, and other roles.
- `extraction_runs`: model/prompt metadata and validated JSON output as `JSONB`.

`source_enterprise_number` is treated as folder provenance metadata. It is not
assumed to be the enterprise number of every company mentioned inside a PDF.
`extracted_enterprise_number` is kept separately when the deed text itself
contains an enterprise number.

Full schema reasoning is in `docs/database_design.md`.

## 2. Setup

This section covers the full pipeline: OCR and Gemini extraction locally, then
PostgreSQL and the API in Docker.

### Prerequisites

Before you start, make sure you have the following installed:

- **WSL** (Ubuntu) with **Python 3.12**
- **Docker Desktop** running
- **Tesseract** and **OCRmyPDF** for scanned PDF processing
- **A Gemini API key** from [Google AI Studio](https://aistudio.google.com/)

Install Tesseract and OCRmyPDF in WSL if you have not already:

```bash
sudo apt install tesseract-ocr tesseract-ocr-fra tesseract-ocr-nld
pip install ocrmypdf --break-system-packages
```

### Step 1 — Get the data

Download the dataset from the challenge repository and place it at:

```text
sagora-deeds/data/
```

The folder structure should look like:

```text
data/
  0267403264/03057415.pdf
  0453983655/1997-09-16_0334.pdf
  0747749937/20324141.pdf
  ...
```

### Step 2 — Configure environment

Copy the example environment file and fill in your Gemini API key:

```bash
cp .env.example .env
```

Open `.env` and set your real key:

```env
GEMINI_API_KEY=your_real_key_here
GEMINI_MODEL=gemini-2.5-flash
DATABASE_URL=postgresql+psycopg://sagora:sagora@localhost:5433/sagora_deeds
OCR_LANGUAGES=fra+nld
```

The database URL uses port `5433` on your host. Docker Compose maps `5433`
on your machine to `5432` inside the container, to avoid conflicts with any
local PostgreSQL installation.

### Step 3 — Create a virtual environment and install dependencies

In WSL, from the project root:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Step 4 — Run the extraction pipeline

**Test with one PDF first** to confirm OCR, Gemini, and Pydantic are all working:

```bash
.venv/bin/python scripts/run_one_pdf.py
```

You should see output like:

```text
Processed: data/0500708654/12305887.pdf
OCR used: False
Deeds extracted: 1
```

**Then run the full 50-PDF batch:**

```bash
.venv/bin/python scripts/run_batch_pdfs.py --limit 50
```

This writes extraction JSON files to `outputs/extractions/` and a summary
report to `outputs/reports/batch_summary_50.json`.

If you need to retry only failed or invalid extractions without re-running
successful ones:

```bash
.venv/bin/python scripts/run_batch_pdfs.py --limit 50 --retry-invalid
```

**Optionally analyze extraction quality:**

```bash
.venv/bin/python scripts/analyze_extractions.py
```

### Step 5 — Start PostgreSQL and the API

```bash
docker compose up --build
```

This starts PostgreSQL on port `5433` and the FastAPI app on port `8000`.
The API container runs Alembic migrations automatically on startup, so the
tables are created before the API accepts requests.

Wait until you see this line in the logs:

```text
Application startup complete.
```

### Step 6 — Load extraction data into PostgreSQL

With Docker still running, open a second terminal and run:

```bash
.venv/bin/python scripts/load_extractions_to_db.py
```

Expected output:

```text
Inserted documents: 50
Skipped existing documents: 0
Total successful artifacts considered: 50
```

The loader is idempotent — running it again skips documents whose SHA-256
hash already exists in the database.

### Step 7 — Verify the data

Check row counts:

```bash
.venv/bin/python scripts/query_db.py --stats
```

Expected:

```text
documents: 50
deeds: 168
companies: 181
party_roles: 574
```

Query by enterprise number or company name:

```bash
.venv/bin/python scripts/query_db.py --enterprise-number 458279072
.venv/bin/python scripts/query_db.py --company-name EUROCAP
```

### Step 8 — Use the API

Swagger docs (interactive):

```text
http://127.0.0.1:8000/docs
```

Available endpoints:

```text
GET /health
GET /stats
GET /companies/{enterprise_number}
GET /companies/{enterprise_number}/decision-makers
GET /companies/{enterprise_number}/mentions
GET /search?query=EURO
```

`/companies/{enterprise_number}/decision-makers` excludes notaries because
notaries are legal intermediaries, not business decision-makers.

## 3. Conclusion / Retrospective

### What Was Built

The final system processes real PDFs into validated JSON, loads that data into a
relational PostgreSQL schema, and exposes it through FastAPI. The API is backed
by the same PostgreSQL database loaded from the 50-PDF extraction batch.

The end-to-end path is:

```text
PDF -> OCR/text -> Gemini JSON -> Pydantic validation -> JSON artifacts
    -> PostgreSQL -> FastAPI
```

### What Worked Well

- The risk-first order worked. OCR/Gemini/Pydantic were proven before database
  and API work started.
- OCR handled the initial scanned sample well enough to process 50 PDFs.
- Pydantic caught invalid/truncated JSON and made batch retry logic possible.
- The 50-PDF batch revealed the real schema shape: many PDFs contain multiple
  notices, and many extracted company rows do not have enterprise numbers.
- PostgreSQL loading is idempotent via `file_hash`.
- FastAPI is a thin wrapper over shared query functions, not a second query
  implementation.

### What Did Not Work or Was Limited

- The first 50-PDF sample is sorted by path, which biases it toward older scanned
  Gazette documents. It is good for OCR risk, but not representative of the full
  dataset.
- Gemini deed type output is inconsistent across languages and casing.
- Dates remain text because OCR and multilingual date formats vary.
- Party-role `confidence` is often null.
- Some API responses expose source `file_path` values for traceability in this
  internal/submission version. A public API should replace those with document
  IDs or download URLs.
- Stage 3 artifacts store validated extraction JSON, not a separate exact raw
  Gemini response.

### Bugs and Blockers

- The first Gemini model configured, `gemini-2.0-flash-lite`, was unavailable
  for new users. I switched to `gemini-2.5-flash`.
- Gemini quota/rate limits required retry handling. The Gemini call now uses
  `tenacity` with exponential backoff for retryable API errors.
- One batch JSON file became truncated during an interrupted run. I added
  `--retry-invalid` and made summary writers use byte writes to avoid stale
  trailing bytes on Windows/WSL.
- Docker initially failed because the API image imported the OCR pipeline through
  package import side effects. I removed that import side effect so the API image
  can stay lightweight.

### Schema Fit for Downstream Use

The schema supports downstream agent-style questions because it separates source
documents, deed notices, companies, and party roles.

Easy queries:

- Find all deed notices for a company enterprise number.
- Find company names matching a search term.
- Retrieve founders/directors/signatories for a company while excluding notaries.
- Count documents, deeds, companies, and party roles for data coverage stats.
- Query raw validated extraction JSON through PostgreSQL `JSONB`.

Harder queries:

- Normalized deed-type analysis, because `deed_type` is still raw multilingual
  model output.
- Accurate date comparisons, because dates are stored as text in v1.
- Full credit-risk analysis, because this dataset does not contain financial
  statements, payment behavior, or default events.

Concrete example: "find all SRLs founded after 2020 with capital over 100k"

The schema is close but not fully ready for this query. `companies.legal_form`
and `companies.capital_amount` make the SRL and capital parts straightforward.
However, `deeds.deed_date` is currently text and `deed_type_normalized` is null,
so "founded after 2020" requires date normalization and deed-type normalization
first. The schema intentionally includes `deed_type_normalized` so that future
cleanup can make this query reliable:

```sql
SELECT c.company_name, c.enterprise_number, c.capital_amount, d.deed_date
FROM companies c
JOIN deeds d ON d.id = c.deed_id
WHERE c.legal_form ILIKE '%SRL%'
  AND c.capital_amount > 100000
  AND d.deed_type_normalized = 'incorporation';
```

With another half-day, I would add a normalization pass for deed types and dates,
then run a broader stratified sample across years so the analysis is less biased
toward old scanned pages.
