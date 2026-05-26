"""Repair deterministic metadata in existing extraction JSON artifacts.

This is a maintenance helper from Stage 4. It exists because source_type became
a pipeline-owned field after earlier artifacts had already been generated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    """Parse the extraction directory to repair."""

    parser = argparse.ArgumentParser(
        description="Repair deterministic metadata in existing extraction JSON files."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "extractions",
        help="Directory containing extraction JSON files.",
    )
    return parser.parse_args()


def infer_source_type(document: dict) -> str:
    """Infer source type from the stored ocr_used flag.

    This Stage 4 repair helper only had enough information to distinguish
    scans from searchable PDFs. It cannot reconstruct the pipeline's "mixed"
    case because older artifacts did not store whether the original PDF already
    had a text layer. Re-running the pipeline is required for exact repair.
    """

    return "scan" if document.get("ocr_used") else "searchable_pdf"


def main() -> int:
    """Update source_type in all extraction JSON files when needed."""

    args = parse_args()
    updated = 0
    unchanged = 0

    for path in sorted(args.dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        source_type = infer_source_type(document)
        if document.get("source_type") == source_type:
            unchanged += 1
            continue

        document["source_type"] = source_type
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        updated += 1

    print(f"Updated: {updated}")
    print(f"Unchanged: {unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
