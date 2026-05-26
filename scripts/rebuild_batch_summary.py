"""Rebuild a batch summary from existing extraction JSON files."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class BatchResult:
    """Serializable summary row reconstructed from one extraction JSON."""

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
    """Parse the summary whose file list should be rebuilt."""

    parser = argparse.ArgumentParser(
        description="Rebuild a batch summary from current extraction JSON files."
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "reports" / "batch_summary_50.json",
        help="Existing batch summary whose file list should be preserved.",
    )
    return parser.parse_args()


def write_csv(path: Path, results: list[BatchResult]) -> None:
    """Write the rebuilt CSV companion report."""

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))


def load_json(path: Path) -> dict:
    """Load JSON and tolerate old files with trailing null bytes."""

    return json.loads(path.read_bytes().rstrip(b"\x00").decode("utf-8"))


def resolve_project_path(path_value: str) -> Path:
    """Resolve relative paths and older absolute paths."""

    path = Path(path_value)
    if path.exists():
        return path
    candidate = PROJECT_ROOT / path_value
    if candidate.exists():
        return candidate

    normalized = path_value.replace("\\", "/")
    marker = f"/{PROJECT_ROOT.name}/"
    if marker in normalized:
        candidate = PROJECT_ROOT / normalized.split(marker, 1)[1]
        if candidate.exists():
            return candidate
    return path


def to_summary_path(path_value: str | None) -> str | None:
    """Normalize stored paths to project-relative form when possible."""

    if path_value is None:
        return None
    path = resolve_project_path(path_value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path_value


def main() -> int:
    """Recalculate summary counts from the current extraction JSON files."""

    args = parse_args()
    summary_path = args.summary.resolve()
    if not summary_path.exists():
        print(f"Summary not found: {summary_path}", file=sys.stderr)
        return 1

    existing = load_json(summary_path)
    rebuilt_results: list[BatchResult] = []

    for result in existing.get("results", []):
        extraction_path = resolve_project_path(result["gemini_json_path"])
        if not extraction_path.exists():
            # Preserve the row but mark it failed if the artifact disappeared.
            rebuilt_results.append(
                BatchResult(
                    input_pdf=to_summary_path(result["input_pdf"]),
                    success=False,
                    ocr_used=None,
                    page_count=None,
                    deeds_extracted=None,
                    companies_extracted=None,
                    party_roles_extracted=None,
                    ocr_text_path=to_summary_path(result.get("ocr_text_path")),
                    gemini_json_path=to_summary_path(result.get("gemini_json_path")),
                    error="Extraction JSON missing.",
                )
            )
            continue

        document = load_json(extraction_path)
        deeds = document.get("deeds", [])
        # Recompute counts from the artifact instead of trusting stale summary values.
        rebuilt_results.append(
            BatchResult(
                input_pdf=to_summary_path(result["input_pdf"]),
                success=True,
                ocr_used=document.get("ocr_used"),
                page_count=document.get("page_count"),
                deeds_extracted=len(deeds),
                companies_extracted=sum(len(deed.get("companies", [])) for deed in deeds),
                party_roles_extracted=sum(len(deed.get("party_roles", [])) for deed in deeds),
                ocr_text_path=to_summary_path(result.get("ocr_text_path")),
                gemini_json_path=to_summary_path(result.get("gemini_json_path")),
                error=None,
            )
        )

    success_count = sum(1 for result in rebuilt_results if result.success)
    failure_count = len(rebuilt_results) - success_count
    deed_counts = [
        result.deeds_extracted or 0 for result in rebuilt_results if result.success
    ]

    rebuilt = {
        "requested_limit": existing.get("requested_limit", len(rebuilt_results)),
        "processed_count": len(rebuilt_results),
        "success_count": success_count,
        "failure_count": failure_count,
        "ocr_success_count": sum(
            1 for result in rebuilt_results if result.success and result.ocr_used
        ),
        "searchable_pdf_success_count": sum(
            1 for result in rebuilt_results if result.success and result.ocr_used is False
        ),
        "multi_notice_success_count": sum(1 for count in deed_counts if count > 1),
        "total_deeds_extracted": sum(deed_counts),
        "total_companies_extracted": sum(
            result.companies_extracted or 0
            for result in rebuilt_results
            if result.success
        ),
        "total_party_roles_extracted": sum(
            result.party_roles_extracted or 0
            for result in rebuilt_results
            if result.success
        ),
        "results": [asdict(result) for result in rebuilt_results],
    }

    summary_path.write_bytes(json.dumps(rebuilt, indent=2).encode("utf-8"))
    csv_path = summary_path.with_suffix(".csv")
    if rebuilt_results:
        write_csv(csv_path, rebuilt_results)

    print(f"Rebuilt JSON summary: {summary_path}")
    print(f"Rebuilt CSV summary: {csv_path}")
    print(f"Successes: {success_count}")
    print(f"Failures: {failure_count}")
    print(f"Deeds extracted: {rebuilt['total_deeds_extracted']}")
    print(f"Party roles extracted: {rebuilt['total_party_roles_extracted']}")
    return 0 if failure_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
