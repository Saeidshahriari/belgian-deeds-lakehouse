"""PDF text extraction and Gemini structured extraction.

The module keeps PDF text detection and PDF text extraction on the same engine
(PyMuPDF) so the "should OCR?" decision cannot disagree with the text reader.
"""

from __future__ import annotations

from pathlib import Path

import fitz
from google import genai
from google.genai import errors
from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from belgian_deed_pipeline.schemas import GeminiExtraction


def get_page_count(pdf_path: Path) -> int:
    """Return the PDF page count using PyMuPDF metadata."""

    with fitz.open(pdf_path) as document:
        return document.page_count


def has_meaningful_text_layer(pdf_path: Path, min_chars: int = 500) -> bool:
    """Decide whether a PDF already has enough text to skip OCR."""

    return len(extract_pdf_text(pdf_path, max_pages=3)) >= min_chars


def extract_pdf_text(pdf_path: Path, max_pages: int | None = None) -> str:
    """Extract text from all pages, or from the first max_pages pages."""

    with fitz.open(pdf_path) as document:
        pages = document if max_pages is None else document[: min(max_pages, document.page_count)]
        return "\n".join(page.get_text() for page in pages).strip()


def build_extraction_prompt(source_file: str) -> str:
    """Build the extraction instructions sent together with OCR text."""

    return f"""
You extract Belgian Gazette company deed data from OCR text.

Source file: {source_file}

Rules:
- Return only data present in the text.
- If a value is missing or uncertain, use null.
- Keep the response strictly aligned with the JSON schema.
- A PDF page may contain one or more notices; return each notice as one deed in deeds[].
- Preserve enterprise numbers exactly as they appear when present.
- Use extracted_enterprise_number only when the deed notice itself clearly states an enterprise number for that notice.
- Do not copy the source folder number into extracted_enterprise_number unless it appears in the OCR text for that notice.
- Keep dates as strings exactly as written if you cannot normalize them safely.
- Keep company and person names in their source language and casing.
- Use publication_reference for Gazette references like 'N. 970916 — 333' or '20010719 — 1004'.
- Use form_reference only for explicit form labels such as Form I, Form II, Volet B, or Luik B.
- Use language codes only: nl, fr, de, mixed, unknown.
- Use party_type only from: person, company, notary, association, unknown.
""".strip()


def is_retryable_gemini_error(exc: BaseException) -> bool:
    """Retry only transient Gemini/API errors, not validation or prompt bugs."""

    if not isinstance(exc, errors.APIError):
        return False
    return getattr(exc, "status_code", None) in {429, 500, 502, 503, 504}


@retry(
    retry=retry_if_exception(is_retryable_gemini_error),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def generate_gemini_content(
    *,
    client: genai.Client,
    model_name: str,
    source_file: str,
    ocr_text: str,
) -> types.GenerateContentResponse:
    """Call Gemini with JSON-schema constrained output and retry protection."""

    return client.models.generate_content(
        model=model_name,
        contents=[
            build_extraction_prompt(source_file),
            ocr_text,
        ],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=GeminiExtraction.model_json_schema(),
        ),
    )


def extract_structured_data(
    *,
    api_key: str,
    model_name: str,
    source_file: str,
    ocr_text: str,
) -> tuple[str, GeminiExtraction]:
    """Return both the raw Gemini JSON and the validated extraction object."""

    client = genai.Client(api_key=api_key)
    response = generate_gemini_content(
        client=client,
        model_name=model_name,
        source_file=source_file,
        ocr_text=ocr_text,
    )

    raw_json = (response.text or "").strip()
    if not raw_json:
        raise ValueError("Gemini returned an empty response.")

    return raw_json, GeminiExtraction.model_validate_json(raw_json)
