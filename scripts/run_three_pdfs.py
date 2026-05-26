"""Stage 1 command: process three representative PDFs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    # Allow direct script execution from the repository checkout.
    sys.path.insert(0, str(SRC_ROOT))

from sagora_deeds.config import load_settings
from sagora_deeds.pipeline import make_artifact_stem, process_pdf


DEFAULT_INPUTS = [
    Path("data/0453983655/1997-09-16_0334.pdf"),
    Path("data/0500708654/12305887.pdf"),
    Path("data/0458279072/2001-07-19_1004.pdf"),
]


@dataclass(slots=True)
class BatchResult:
    """Small printable result object for each Stage 1 PDF."""

    input_pdf: Path
    success: bool
    ocr_used: bool | None = None
    deeds_extracted: int | None = None
    ocr_text_path: Path | None = None
    gemini_json_path: Path | None = None
    error: str | None = None


def parse_args() -> argparse.Namespace:
    """Parse optional PDF paths and OCR behavior."""

    parser = argparse.ArgumentParser(
        description="Run the Stage 1 three-PDF extraction proof."
    )
    parser.add_argument(
        "--input",
        type=Path,
        nargs="*",
        default=DEFAULT_INPUTS,
        help="PDFs to process. Defaults to three real samples from the dataset.",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Force OCR on all PDFs even if a readable text layer exists.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the three-PDF proof and print one block per PDF."""

    args = parse_args()
    settings = load_settings()

    extraction_dir = settings.project_root / "outputs" / "extractions"
    ocr_text_dir = settings.project_root / "outputs" / "ocr_text"
    processed_pdf_dir = settings.project_root / "outputs" / "ocr_pdfs"

    results: list[BatchResult] = []
    for raw_input in args.input:
        # Each sample writes to the same artifact layout used by larger batches.
        input_pdf = (settings.project_root / raw_input).resolve()
        stem = make_artifact_stem(input_pdf)
        ocr_text_path = ocr_text_dir / f"{stem}.txt"
        gemini_json_path = extraction_dir / f"{stem}.json"
        processed_pdf_path = processed_pdf_dir / f"{stem}_ocr.pdf"

        if not input_pdf.exists():
            results.append(
                BatchResult(
                    input_pdf=input_pdf,
                    success=False,
                    error="Input PDF not found.",
                )
            )
            continue

        try:
            # Keep failures isolated so one bad PDF does not hide the others.
            artifacts = process_pdf(
                input_pdf=input_pdf,
                settings=settings,
                ocr_text_path=ocr_text_path,
                gemini_json_path=gemini_json_path,
                processed_pdf_path=processed_pdf_path,
                force_ocr=args.force_ocr,
            )
            results.append(
                BatchResult(
                    input_pdf=input_pdf,
                    success=True,
                    ocr_used=artifacts.ocr_used,
                    deeds_extracted=len(artifacts.validated_document.deeds),
                    ocr_text_path=artifacts.ocr_text_path,
                    gemini_json_path=artifacts.gemini_json_path,
                )
            )
        except Exception as exc:
            results.append(
                BatchResult(
                    input_pdf=input_pdf,
                    success=False,
                    ocr_text_path=ocr_text_path if ocr_text_path.exists() else None,
                    gemini_json_path=gemini_json_path if gemini_json_path.exists() else None,
                    error=str(exc),
                )
            )

    for result in results:
        print(f"PDF: {result.input_pdf}")
        print(f"Success: {result.success}")
        if result.ocr_used is not None:
            print(f"OCR used: {result.ocr_used}")
        if result.deeds_extracted is not None:
            print(f"Deeds extracted: {result.deeds_extracted}")
        if result.ocr_text_path is not None:
            print(f"OCR text: {result.ocr_text_path}")
        if result.gemini_json_path is not None:
            print(f"Gemini JSON: {result.gemini_json_path}")
        if result.error:
            print(f"Error: {result.error}")
        print("")

    success_count = sum(1 for result in results if result.success)
    print(f"Completed {success_count}/{len(results)} PDFs successfully.")
    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
