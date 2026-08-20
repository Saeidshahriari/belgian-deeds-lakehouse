"""Stage 0 command: process one real PDF end-to-end."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    # Allow running the script directly without installing the package first.
    sys.path.insert(0, str(SRC_ROOT))

from belgian_deed_pipeline.config import load_settings
from belgian_deed_pipeline.pipeline import process_one_pdf


DEFAULT_SAMPLE = Path("data/0500708654/12305887.pdf")


def parse_args() -> argparse.Namespace:
    """Parse the one-PDF spike options."""

    parser = argparse.ArgumentParser(
        description="Run the Stage 0 one-PDF extraction pipeline."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SAMPLE,
        help="PDF to process. Defaults to a real sample from the dataset.",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Force OCR even when the PDF already has a readable text layer.",
    )
    return parser.parse_args()


def main() -> int:
    """Run one PDF through OCR/text extraction, Gemini, and Pydantic validation."""

    args = parse_args()
    settings = load_settings()
    input_pdf = (settings.project_root / args.input).resolve()

    if not input_pdf.exists():
        print(f"Input PDF not found: {input_pdf}", file=sys.stderr)
        return 1

    artifacts = process_one_pdf(
        input_pdf=input_pdf,
        settings=settings,
        force_ocr=args.force_ocr,
    )

    print(f"Processed: {artifacts.input_pdf}")
    print(f"OCR used: {artifacts.ocr_used}")
    print(f"OCR text: {artifacts.ocr_text_path}")
    print(f"Gemini JSON: {artifacts.gemini_json_path}")
    print(f"Deeds extracted: {len(artifacts.validated_document.deeds)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
