# Stage 4 Database Design

This schema is based on the first 50 processed PDFs, not on the initial brief alone.

Observed batch results:

- 50 PDFs processed successfully.
- 50/50 required OCR.
- 49/50 PDFs contained more than one deed notice.
- 167 deed notices were extracted.
- 181 company records were extracted.
- 586 party role records were extracted.
- Only 61/181 company records had an extracted enterprise number.
- Party role confidence was missing for most rows.

The main design decision is that a PDF document is not equivalent to a company
or a deed. Belgian Gazette pages often contain multiple notices, and notices can
mention multiple companies and parties.

## Tables

### documents

One row per source PDF.

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID | Primary key |
| source_enterprise_number | VARCHAR(10), nullable | Enterprise number from the dataset folder, not necessarily extracted from the text |
| file_name | TEXT | Original PDF filename |
| file_path | TEXT | Source path inside the project or mounted data volume |
| file_hash | TEXT | Hash of the source PDF for deduplication |
| page_count | INTEGER | PDF page count |
| source_type | TEXT | `scan`, `searchable_pdf`, `mixed`, or `unknown` |
| ocr_used | BOOLEAN | Whether OCR was used for this document |
| ocr_status | TEXT | `success`, `failed`, or `skipped` |
| ocr_text_path | TEXT, nullable | Path to extracted OCR/text output |
| processing_status | TEXT | `success`, `failed`, or `partial` |
| error_message | TEXT, nullable | Processing error if any |
| created_at | TIMESTAMPTZ | Insert timestamp |

`source_enterprise_number` comes from the folder name, for example
`data/0459609754/...`. It is provenance metadata, not a claim that every deed or
company mentioned inside the PDF has that enterprise number.

### deeds

One row per deed notice extracted from a document.

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID | Primary key |
| document_id | UUID | Foreign key to `documents.id` |
| source_enterprise_number | VARCHAR(10), nullable | Copied from the source document folder for traceability |
| extracted_enterprise_number | TEXT, nullable | Enterprise number if Gemini/OCR explicitly extracted one at deed level |
| deed_type | TEXT, nullable | Raw deed type from Gemini |
| deed_type_normalized | TEXT, nullable | Cleaned value such as `incorporation`, `capital_change`, `appointment`; can be filled later |
| deed_date | TEXT, nullable | Kept as text for v1 because OCR date formats vary |
| publication_date | TEXT, nullable | Kept as text for v1 because OCR date formats vary |
| publication_reference | TEXT, nullable | Gazette notice reference, for example `N. 970916 - 333` |
| form_reference | TEXT, nullable | Actual form label such as `Form I`, `Volet B`, or `Luik B` |
| language | TEXT, nullable | `nl`, `fr`, `de`, `mixed`, or `unknown` |
| summary | TEXT, nullable | Short Gemini summary |
| created_at | TIMESTAMPTZ | Insert timestamp |

`deed_type` intentionally stores the raw model output. The batch showed values
such as `CONSTITUTION`, `Constitution`, `Oprichting`, and `OPRICHTING` for the
same broad concept. `deed_type_normalized` is included now so Stage 5 can insert
raw values immediately while leaving a stable place for later cleanup.

### companies

One row per company mention inside a deed.

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID | Primary key |
| deed_id | UUID | Foreign key to `deeds.id` |
| enterprise_number | TEXT, nullable | Extracted enterprise number when present |
| company_name | TEXT, nullable | Extracted company name |
| legal_form | TEXT, nullable | Raw legal form text |
| registered_office_address | TEXT, nullable | Extracted address |
| postal_code | TEXT, nullable | Extracted postal code |
| city | TEXT, nullable | Extracted city |
| country | TEXT, nullable | Extracted country |
| corporate_purpose | TEXT, nullable | Extracted corporate purpose |
| capital_amount | NUMERIC, nullable | Extracted capital amount |
| capital_currency | TEXT, nullable | Extracted currency |
| created_at | TIMESTAMPTZ | Insert timestamp |

Companies reference `deed_id`, not only `enterprise_number`, because 120/181
company rows in the first batch did not have an extracted enterprise number.

### party_roles

One row per person/company/association role inside a deed.

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID | Primary key |
| deed_id | UUID | Foreign key to `deeds.id` |
| name | TEXT, nullable | Party name |
| party_type | TEXT, nullable | `person`, `company`, `notary`, `association`, or `unknown` |
| role | TEXT, nullable | Raw role text |
| address | TEXT, nullable | Extracted address |
| start_date | TEXT, nullable | Kept as text for v1 |
| end_date | TEXT, nullable | Kept as text for v1 |
| confidence | NUMERIC, nullable | Gemini confidence when returned |
| raw_context | TEXT, nullable | Supporting source text |
| created_at | TIMESTAMPTZ | Insert timestamp |

`confidence` is intentionally nullable. In the first 50-PDF batch, most party
roles had no confidence value. The column stays because it is useful when present,
but Stage 5 should not spend time forcing confidence generation.

### extraction_runs

One row per model extraction attempt for a document.

| Column | Type | Notes |
| --- | --- | --- |
| id | UUID | Primary key |
| document_id | UUID | Foreign key to `documents.id` |
| model_name | TEXT | Gemini model used |
| prompt_version | TEXT | Prompt/schema version |
| ocr_used | BOOLEAN | Whether OCR was used |
| raw_gemini_response | JSONB | Raw Gemini JSON response |
| validated | BOOLEAN | Whether Pydantic validation passed |
| validation_error | TEXT, nullable | Validation error if any |
| created_at | TIMESTAMPTZ | Insert timestamp |

`raw_gemini_response` should be `JSONB`, not `TEXT`, so later analysis can query
inside model outputs without reparsing files.

## Relationships

- `documents` 1-to-many `deeds`
- `deeds` 1-to-many `companies`
- `deeds` 1-to-many `party_roles`
- `documents` 1-to-many `extraction_runs`

## Indexes

Minimum useful indexes for Stage 5:

```sql
CREATE INDEX ix_documents_file_hash ON documents(file_hash);
CREATE INDEX ix_documents_source_enterprise_number ON documents(source_enterprise_number);
CREATE INDEX ix_deeds_document_id ON deeds(document_id);
CREATE INDEX ix_deeds_source_enterprise_number ON deeds(source_enterprise_number);
CREATE INDEX ix_deeds_publication_reference ON deeds(publication_reference);
CREATE INDEX ix_companies_deed_id ON companies(deed_id);
CREATE INDEX ix_companies_enterprise_number ON companies(enterprise_number);
CREATE INDEX ix_party_roles_deed_id ON party_roles(deed_id);
CREATE INDEX ix_extraction_runs_document_id ON extraction_runs(document_id);
```

Optional later indexes:

```sql
CREATE INDEX ix_deeds_deed_type_normalized ON deeds(deed_type_normalized);
CREATE INDEX ix_deeds_language ON deeds(language);
CREATE INDEX ix_companies_company_name ON companies(company_name);
CREATE INDEX ix_party_roles_name ON party_roles(name);
```

## Known Limitations

- `deed_type` is not normalized yet. The schema includes `deed_type_normalized`
  to support later cleanup.
- `source_enterprise_number` is folder metadata. It must not be confused with an
  enterprise number explicitly extracted from the deed text.
- Dates remain text in v1 because OCR and multilingual date formats vary.
- `confidence` is mostly null in current Gemini output.
- Some PDFs contain unrelated Gazette notices. This is expected and is why deeds
  are modeled as child rows of documents.
- Enterprise numbers are often missing from extracted companies in old scanned
  notices.
- The first 50-PDF sample was selected by sorted path order, which biased the
  sample toward older scanned Gazette documents. It is useful for OCR risk, but
  it should not be treated as representative of the whole dataset.
- Batch extraction is resumable at the JSON artifact level. Existing extraction
  files should be reused unless an explicit overwrite is requested.
- Stage 3 artifacts contain validated extraction JSON, not a separate exact raw
  Gemini response. Stage 5 stores that JSON in `raw_gemini_response` for the
  current batch; future pipeline runs can persist exact raw model output as a
  separate artifact if needed.
