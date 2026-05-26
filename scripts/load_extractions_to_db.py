"""Stage 5 command: load validated extraction JSON into PostgreSQL."""

from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    # Allow direct execution from the repository without installation.
    sys.path.insert(0, str(SRC_ROOT))

from sqlalchemy import select

from sagora_deeds.config import load_database_url
from sagora_deeds.db.models import Company, Deed, Document, ExtractionRun, PartyRole
from sagora_deeds.db.session import make_session_factory
from sagora_deeds.schemas import DocumentExtraction


PROMPT_VERSION = "stage5-gemini-extraction-v1"


def parse_args() -> argparse.Namespace:
    """Parse the summary file and model metadata to store in extraction_runs."""

    parser = argparse.ArgumentParser(
        description="Load extraction JSON artifacts into PostgreSQL."
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "reports" / "batch_summary_50.json",
        help="Batch summary JSON that contains source PDF and extraction artifact paths.",
    )
    parser.add_argument(
        "--model-name",
        default="gemini-2.5-flash",
        help="Model name to record in extraction_runs.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    """Hash source PDFs for document-level idempotency."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_enterprise_number_from_path(path: Path) -> str | None:
    """Read the source enterprise number from the dataset folder name."""

    parent = path.parent.name.strip()
    if parent.isdigit() and len(parent) == 10:
        return parent
    return None


def decimal_or_none(value: float | int | str | None) -> Decimal | None:
    """Convert numeric extraction values to Decimal for PostgreSQL Numeric."""

    if value is None or value == "":
        return None
    return Decimal(str(value))


def load_summary(path: Path) -> dict:
    """Load the batch summary selected for database import."""

    if not path.exists():
        raise FileNotFoundError(f"Summary not found: {path}")
    return load_json(path)


def load_json(path: Path) -> dict:
    """Load JSON and tolerate old files with trailing null bytes."""

    return json.loads(path.read_bytes().rstrip(b"\x00").decode("utf-8"))


def resolve_project_path(path_value: str) -> Path:
    """Resolve current relative paths and older absolute WSL paths."""

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


def insert_document_from_result(
    *,
    session,
    result: dict,
    model_name: str,
) -> bool:
    """Insert one successful extraction result, returning False if already loaded."""

    pdf_path = resolve_project_path(result["input_pdf"])
    extraction_path = resolve_project_path(result["gemini_json_path"])
    if not pdf_path.exists():
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")
    if not extraction_path.exists():
        raise FileNotFoundError(f"Extraction JSON not found: {extraction_path}")

    file_hash = sha256_file(pdf_path)
    existing = session.scalar(select(Document).where(Document.file_hash == file_hash))
    if existing is not None:
        # Idempotency: rerunning the loader should not duplicate rows.
        return False

    payload = load_json(extraction_path)
    extraction = DocumentExtraction.model_validate(payload)
    source_enterprise_number = source_enterprise_number_from_path(pdf_path)

    document = Document(
        source_enterprise_number=source_enterprise_number,
        file_name=pdf_path.name,
        file_path=str(pdf_path),
        file_hash=file_hash,
        page_count=extraction.page_count,
        source_type=extraction.source_type,
        ocr_used=extraction.ocr_used,
        ocr_status="success" if extraction.ocr_used else "skipped",
        ocr_text_path=str(resolve_project_path(result["ocr_text_path"]))
        if result.get("ocr_text_path")
        else None,
        processing_status="success",
        error_message=None,
    )
    session.add(document)

    # Deeds own companies and party roles through ORM relationships.
    for extracted_deed in extraction.deeds:
        deed = Deed(
            document=document,
            source_enterprise_number=source_enterprise_number,
            extracted_enterprise_number=extracted_deed.extracted_enterprise_number,
            deed_type=extracted_deed.deed_type,
            deed_type_normalized=None,
            deed_date=extracted_deed.deed_date,
            publication_date=extracted_deed.publication_date,
            publication_reference=extracted_deed.publication_reference,
            form_reference=extracted_deed.form_reference,
            language=extracted_deed.language,
            summary=extracted_deed.summary,
        )
        session.add(deed)

        for extracted_company in extracted_deed.companies:
            session.add(
                Company(
                    deed=deed,
                    enterprise_number=extracted_company.enterprise_number,
                    company_name=extracted_company.company_name,
                    legal_form=extracted_company.legal_form,
                    registered_office_address=extracted_company.registered_office_address,
                    postal_code=extracted_company.postal_code,
                    city=extracted_company.city,
                    country=extracted_company.country,
                    corporate_purpose=extracted_company.corporate_purpose,
                    capital_amount=decimal_or_none(extracted_company.capital_amount),
                    capital_currency=extracted_company.capital_currency,
                )
            )

        for extracted_party in extracted_deed.party_roles:
            session.add(
                PartyRole(
                    deed=deed,
                    name=extracted_party.name,
                    party_type=extracted_party.party_type,
                    role=extracted_party.role,
                    address=extracted_party.address,
                    start_date=extracted_party.start_date,
                    end_date=extracted_party.end_date,
                    confidence=decimal_or_none(extracted_party.confidence),
                    raw_context=extracted_party.raw_context,
                )
            )

    session.add(
        ExtractionRun(
            document=document,
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            ocr_used=extraction.ocr_used,
            raw_gemini_response=payload,
            validated=True,
            validation_error=None,
        )
    )
    return True


def main() -> int:
    """Load all successful batch artifacts and commit them in one transaction."""

    args = parse_args()
    summary = load_summary(args.summary)
    results = [result for result in summary.get("results", []) if result.get("success")]

    session_factory = make_session_factory(load_database_url())
    inserted = 0
    skipped = 0

    with session_factory() as session:
        for result in results:
            if insert_document_from_result(
                session=session,
                result=result,
                model_name=args.model_name,
            ):
                inserted += 1
            else:
                skipped += 1
        session.commit()

    print(f"Inserted documents: {inserted}")
    print(f"Skipped existing documents: {skipped}")
    print(f"Total successful artifacts considered: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
