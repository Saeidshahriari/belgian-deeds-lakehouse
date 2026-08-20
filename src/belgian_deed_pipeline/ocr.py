"""OCR wrapper around the OCRmyPDF command-line tool."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def resolve_ocrmypdf_executable() -> str:
    """Prefer the virtualenv executable, then fall back to PATH."""

    candidate = Path(sys.executable).parent / "ocrmypdf"
    if candidate.exists():
        return str(candidate)
    return "ocrmypdf"


def run_ocr(input_pdf: Path, output_pdf: Path, languages: str) -> None:
    """Create a searchable PDF from a scanned PDF.

    OCRmyPDF writes a new PDF instead of modifying the input file. The pipeline
    then extracts text from this processed PDF with the same PyMuPDF path used
    for originally searchable PDFs.
    """

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    # --deskew improves OCR on old Gazette scans that are slightly rotated.
    subprocess.run(
        [
            resolve_ocrmypdf_executable(),
            "-l",
            languages,
            "--deskew",
            str(input_pdf),
            str(output_pdf),
        ],
        check=True,
    )
