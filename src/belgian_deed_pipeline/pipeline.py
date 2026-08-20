"""End-to-end PDF processing pipeline.

This is the core vertical slice: source PDF -> text/OCR -> Gemini extraction ->
Pydantic-validated JSON artifact. Database and API code depend on the artifacts
produced here, not on direct calls to Gemini.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from belgian_deed_pipeline.config import Settings
from belgian_deed_pipeline.extract import (
    extract_pdf_text,
    extract_structured_data,
    get_page_count,
    has_meaningful_text_layer,
)
from belgian_deed_pipeline.ocr import run_ocr
from belgian_deed_pipeline.schemas import DocumentExtraction
from belgian_deed_pipeline.security import ScanResult, scan_pdf, scan_text_for_injection


@dataclass(slots=True)
class ProcessedPdfArtifacts:
    """Paths and validated data produced by one PDF processing run."""

    input_pdf: Path
    processed_pdf: Path
    ocr_text_path: Path
    gemini_json_path: Path
    ocr_used: bool
    raw_gemini_json: str
    validated_document: DocumentExtraction
    scan_result: ScanResult


def make_artifact_stem(input_pdf: Path) -> str:
    """Create stable output names from folder enterprise number and file name."""

    safe_parent = re.sub(r"[^A-Za-z0-9._-]+", "_", input_pdf.parent.name)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", input_pdf.stem)
    return f"{safe_parent}__{safe_name}"


def infer_source_type(*, ocr_used: bool, had_text_layer: bool) -> str:
    """Classify the document source from pipeline facts, not Gemini output."""

    if ocr_used and had_text_layer:
        return "mixed"
    if ocr_used:
        return "scan"
    return "searchable_pdf"


def process_pdf(
    *,
    input_pdf: Path,
    settings: Settings,
    ocr_text_path: Path,
    gemini_json_path: Path,
    processed_pdf_path: Path | None = None,
    force_ocr: bool = False,
) -> ProcessedPdfArtifacts:
    """Process one PDF and write OCR text plus validated extraction JSON."""

    input_pdf = input_pdf.resolve()
    page_count = get_page_count(input_pdf)

    # Security gate: inspect the raw PDF structure before trusting the file.
    # This runs first so active content is flagged even if later steps fail.
    scan_result = scan_pdf(input_pdf)

    ocr_text_path.parent.mkdir(parents=True, exist_ok=True)
    gemini_json_path.parent.mkdir(parents=True, exist_ok=True)
    if processed_pdf_path is not None:
        processed_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # Detect text before OCR so source_type can distinguish scans from text PDFs.
    had_text_layer = has_meaningful_text_layer(input_pdf)
    ocr_used = force_ocr or not had_text_layer

    if ocr_used:
        if processed_pdf_path is None:
            raise ValueError("processed_pdf_path is required when OCR is needed.")
        run_ocr(input_pdf, processed_pdf_path, settings.ocr_languages)
        text_source = processed_pdf_path
        processed_pdf = processed_pdf_path
    else:
        text_source = input_pdf
        processed_pdf = input_pdf

    ocr_text = extract_pdf_text(text_source)
    ocr_text_path.write_text(ocr_text, encoding="utf-8")

    # Second security gate: scan the extracted text for prompt-injection payloads
    # before it is sent to Gemini. The text only exists after OCR, so this runs here.
    scan_result.findings.extend(scan_text_for_injection(ocr_text))

    # Gemini only returns extracted deed data; pipeline-owned metadata is added below.
    raw_json, gemini_extraction = extract_structured_data(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
        source_file=input_pdf.name,
        ocr_text=ocr_text,
    )
    # These fields are deterministic pipeline facts, so Gemini does not control them.
    validated_document = DocumentExtraction(
        source_file=input_pdf.name,
        page_count=page_count,
        ocr_used=ocr_used,
        source_type=infer_source_type(
            ocr_used=ocr_used,
            had_text_layer=had_text_layer,
        ),
        deeds=gemini_extraction.deeds,
    )

    gemini_json_path.write_text(
        validated_document.model_dump_json(indent=2),
        encoding="utf-8",
    )

    return ProcessedPdfArtifacts(
        input_pdf=input_pdf,
        processed_pdf=processed_pdf,
        ocr_text_path=ocr_text_path,
        gemini_json_path=gemini_json_path,
        ocr_used=ocr_used,
        raw_gemini_json=raw_json,
        validated_document=validated_document,
        scan_result=scan_result,
    )


def process_one_pdf(
    *,
    input_pdf: Path,
    settings: Settings,
    force_ocr: bool = False,
) -> ProcessedPdfArtifacts:
    """Run the Stage 0 one-PDF spike with fixed debug artifact paths."""

    settings.debug_dir.mkdir(parents=True, exist_ok=True)
    return process_pdf(
        input_pdf=input_pdf,
        settings=settings,
        ocr_text_path=settings.debug_dir / "one_pdf_ocr.txt",
        gemini_json_path=settings.debug_dir / "one_pdf_gemini.json",
        processed_pdf_path=settings.debug_dir / "one_pdf_processed.pdf",
        force_ocr=force_ocr,
    )
