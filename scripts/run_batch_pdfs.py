"""Stage 3 command: process a batch of PDFs into extraction JSON files."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    # Allow direct script execution without requiring pip install -e .
    sys.path.insert(0, str(SRC_ROOT))

from sagora_deeds.config import load_settings
from sagora_deeds.pipeline import make_artifact_stem, process_pdf
from sagora_deeds.schemas import DocumentExtraction


@dataclass(slots=True)
class BatchResult:
    """Serializable per-PDF result written into the batch summary."""

    input_pdf: str
    success: bool
    ocr_used: bool | None
    page_count: int | None
    deeds_extracted: int | None
    companies_extracted: int | None
    party_roles_extracted: int | None
    ocr_text_path: str | None
    gemini_json_path: str | None
    error: str | None


def parse_args() -> argparse.Namespace:
    """Parse batch size and reprocessing behavior."""

    parser = argparse.ArgumentParser(
        description="Run the Stage 3 batch extraction over a sample of PDFs."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of PDFs to process from data/, in sorted order.",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Force OCR on all PDFs even if a readable text layer exists.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reprocess PDFs even when an extraction JSON already exists.",
    )
    parser.add_argument(
        "--retry-invalid",
        action="store_true",
        help="Reprocess only missing or invalid extraction JSON files.",
    )
    return parser.parse_args()


def iter_pdfs(data_dir: Path, limit: int) -> list[Path]:
    """Return the first N PDFs in deterministic sorted order."""

    return sorted(data_dir.rglob("*.pdf"))[:limit]


def write_summary_json(summary_path: Path, payload: dict) -> None:
    """Write JSON using bytes to avoid stale trailing bytes on Windows/WSL."""

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_bytes(json.dumps(payload, indent=2).encode("utf-8"))


def summary_path(project_root: Path, path: Path) -> str:
    """Store portable project-relative paths in summary files when possible."""

    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def write_summary_csv(summary_path: Path, results: list[BatchResult]) -> None:
    """Write a CSV companion report for quick spreadsheet inspection."""

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def result_from_existing_json(
    *,
    project_root: Path,
    input_pdf: Path,
    ocr_text_path: Path,
    gemini_json_path: Path,
) -> BatchResult:
    """Build a BatchResult from an existing valid extraction JSON."""

    document = DocumentExtraction.model_validate_json(
        gemini_json_path.read_text(encoding="utf-8")
    )
    deeds = document.deeds
    return BatchResult(
        input_pdf=summary_path(project_root, input_pdf),
        success=True,
        ocr_used=document.ocr_used,
        page_count=document.page_count,
        deeds_extracted=len(deeds),
        companies_extracted=sum(len(deed.companies) for deed in deeds),
        party_roles_extracted=sum(len(deed.party_roles) for deed in deeds),
        ocr_text_path=summary_path(project_root, ocr_text_path)
        if ocr_text_path.exists()
        else None,
        gemini_json_path=summary_path(project_root, gemini_json_path),
        error=None,
    )


def existing_json_is_valid(path: Path) -> bool:
    """Return True only when the existing artifact still matches the schema."""

    if not path.exists():
        return False
    try:
        DocumentExtraction.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return True


def main() -> int:
    """Run or reuse batch extractions and write JSON/CSV summary reports."""

    args = parse_args()
    settings = load_settings()

    input_pdfs = iter_pdfs(settings.project_root / "data", args.limit)
    extraction_dir = settings.project_root / "outputs" / "extractions"
    ocr_text_dir = settings.project_root / "outputs" / "ocr_text"
    processed_pdf_dir = settings.project_root / "outputs" / "ocr_pdfs"
    report_dir = settings.project_root / "outputs" / "reports"

    results: list[BatchResult] = []
    reused_existing_count = 0
    for input_pdf in input_pdfs:
        # Output names include the parent folder enterprise number to avoid collisions.
        stem = make_artifact_stem(input_pdf)
        ocr_text_path = ocr_text_dir / f"{stem}.txt"
        gemini_json_path = extraction_dir / f"{stem}.json"
        processed_pdf_path = processed_pdf_dir / f"{stem}_ocr.pdf"

        try:
            # Normal reruns are cheap: reuse valid JSON unless explicitly asked otherwise.
            if (
                gemini_json_path.exists()
                and not args.overwrite
                and not args.retry_invalid
            ):
                reused_existing_count += 1
                results.append(
                    result_from_existing_json(
                        project_root=settings.project_root,
                        input_pdf=input_pdf,
                        ocr_text_path=ocr_text_path,
                        gemini_json_path=gemini_json_path,
                    )
                )
                continue
            if args.retry_invalid and existing_json_is_valid(gemini_json_path):
                # --retry-invalid only spends Gemini quota on missing/broken artifacts.
                reused_existing_count += 1
                results.append(
                    result_from_existing_json(
                        project_root=settings.project_root,
                        input_pdf=input_pdf,
                        ocr_text_path=ocr_text_path,
                        gemini_json_path=gemini_json_path,
                    )
                )
                continue

            artifacts = process_pdf(
                input_pdf=input_pdf,
                settings=settings,
                ocr_text_path=ocr_text_path,
                gemini_json_path=gemini_json_path,
                processed_pdf_path=processed_pdf_path,
                force_ocr=args.force_ocr,
            )
            deeds = artifacts.validated_document.deeds
            companies_extracted = sum(len(deed.companies) for deed in deeds)
            party_roles_extracted = sum(len(deed.party_roles) for deed in deeds)
            results.append(
                BatchResult(
                    input_pdf=summary_path(settings.project_root, input_pdf),
                    success=True,
                    ocr_used=artifacts.ocr_used,
                    page_count=artifacts.validated_document.page_count,
                    deeds_extracted=len(deeds),
                    companies_extracted=companies_extracted,
                    party_roles_extracted=party_roles_extracted,
                    ocr_text_path=summary_path(settings.project_root, artifacts.ocr_text_path),
                    gemini_json_path=summary_path(
                        settings.project_root,
                        artifacts.gemini_json_path,
                    ),
                    error=None,
                )
            )
        except Exception as exc:
            results.append(
                BatchResult(
                    input_pdf=summary_path(settings.project_root, input_pdf),
                    success=False,
                    ocr_used=None,
                    page_count=None,
                    deeds_extracted=None,
                    companies_extracted=None,
                    party_roles_extracted=None,
                    ocr_text_path=summary_path(settings.project_root, ocr_text_path)
                    if ocr_text_path.exists()
                    else None,
                    gemini_json_path=summary_path(settings.project_root, gemini_json_path)
                    if gemini_json_path.exists()
                    else None,
                    error=str(exc),
                )
            )

    success_count = sum(1 for result in results if result.success)
    failure_count = len(results) - success_count
    ocr_successes = [result for result in results if result.success and result.ocr_used]
    non_ocr_successes = [result for result in results if result.success and result.ocr_used is False]
    deed_counts = [result.deeds_extracted or 0 for result in results if result.success]
    multi_notice_count = sum(1 for count in deed_counts if count > 1)

    summary_payload = {
        "requested_limit": args.limit,
        "processed_count": len(results),
        "success_count": success_count,
        "failure_count": failure_count,
        "ocr_success_count": len(ocr_successes),
        "searchable_pdf_success_count": len(non_ocr_successes),
        "multi_notice_success_count": multi_notice_count,
        "total_deeds_extracted": sum(deed_counts),
        "total_companies_extracted": sum(
            result.companies_extracted or 0 for result in results if result.success
        ),
        "total_party_roles_extracted": sum(
            result.party_roles_extracted or 0 for result in results if result.success
        ),
        "reused_existing_count": reused_existing_count,
        "results": [asdict(result) for result in results],
    }

    json_summary_path = report_dir / f"batch_summary_{args.limit}.json"
    csv_summary_path = report_dir / f"batch_summary_{args.limit}.csv"
    write_summary_json(json_summary_path, summary_payload)
    if results:
        write_summary_csv(csv_summary_path, results)

    print(f"Processed: {len(results)} PDFs")
    print(f"Successes: {success_count}")
    print(f"Failures: {failure_count}")
    print(f"OCR successes: {len(ocr_successes)}")
    print(f"Searchable PDF successes: {len(non_ocr_successes)}")
    print(f"Multi-notice successes: {multi_notice_count}")
    print(f"Reused existing JSON: {reused_existing_count}")
    print(f"JSON summary: {json_summary_path}")
    print(f"CSV summary: {csv_summary_path}")
    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
