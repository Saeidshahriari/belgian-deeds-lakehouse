"""Shared database queries used by both the CLI and the FastAPI layer."""

from __future__ import annotations

import re
from typing import NamedTuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from sagora_deeds.db.models import Company, Deed, Document, PartyRole


class CompanySearchRow(NamedTuple):
    """Company search result with its deed and source document."""

    company: Company
    deed: Deed
    document: Document


class DecisionMakerRow(NamedTuple):
    """Decision-maker result with the deed and source document."""

    party_role: PartyRole
    deed: Deed
    document: Document


def normalize_enterprise_number(value: str) -> str:
    """Normalize user input such as BE 0458.279.072 to digits only."""

    cleaned = re.sub(r"[^0-9]", "", value.upper().removeprefix("BE"))
    return cleaned


def enterprise_number_expression(column):
    """Apply the same enterprise-number normalization in SQL.

    Stored values are inconsistent: examples include BE 458.279.072,
    458,279,072, and 0458279072. This expression strips non-digits so stored
    values and user input compare equally. It prevents normal index use on the
    column, which is acceptable at the current 50-document scale.
    """

    without_be = func.regexp_replace(func.upper(column), "^BE", "")
    return func.regexp_replace(without_be, "[^0-9]", "", "g")


def get_stats(session: Session) -> dict[str, int]:
    """Return simple row counts used by the CLI, API, and smoke tests."""

    return {
        "documents": session.scalar(select(func.count()).select_from(Document)) or 0,
        "deeds": session.scalar(select(func.count()).select_from(Deed)) or 0,
        "companies": session.scalar(select(func.count()).select_from(Company)) or 0,
        "party_roles": session.scalar(select(func.count()).select_from(PartyRole)) or 0,
    }


def search_companies_by_name(
    session: Session,
    query: str,
    *,
    limit: int = 25,
) -> list[CompanySearchRow]:
    """Search company names with a case-insensitive substring match."""

    stmt = (
        select(Company, Deed, Document)
        .join(Deed, Company.deed_id == Deed.id)
        .join(Document, Deed.document_id == Document.id)
        .where(Company.company_name.ilike(f"%{query}%"))
        .order_by(Company.company_name)
        .limit(limit)
    )
    return [CompanySearchRow(*row) for row in session.execute(stmt)]


def find_company_mentions_by_enterprise_number(
    session: Session,
    enterprise_number: str,
    *,
    limit: int = 100,
) -> list[CompanySearchRow]:
    """Find company/deed/document rows by any relevant enterprise-number source."""

    normalized = normalize_enterprise_number(enterprise_number)
    stmt = (
        select(Company, Deed, Document)
        .join(Deed, Company.deed_id == Deed.id)
        .join(Document, Deed.document_id == Document.id)
        .where(
            or_(
                enterprise_number_expression(Company.enterprise_number) == normalized,
                enterprise_number_expression(Deed.extracted_enterprise_number) == normalized,
                enterprise_number_expression(Deed.source_enterprise_number) == normalized,
                enterprise_number_expression(Document.source_enterprise_number) == normalized,
            )
        )
        .order_by(Document.file_name, Deed.publication_reference)
        .limit(limit)
    )
    return [CompanySearchRow(*row) for row in session.execute(stmt)]


def get_company_profile(
    session: Session,
    enterprise_number: str,
) -> dict | None:
    """Build the company profile response from matching company mentions."""

    rows = find_company_mentions_by_enterprise_number(
        session,
        enterprise_number,
        limit=100,
    )
    if not rows:
        return None

    seen_documents: dict[str, Document] = {}
    seen_deeds: dict[str, Deed] = {}
    companies: list[Company] = []
    for company, deed, document in rows:
        seen_documents[str(document.id)] = document
        seen_deeds[str(deed.id)] = deed
        companies.append(company)

    return {
        "enterprise_number": enterprise_number,
        "companies": companies,
        "deeds": list(seen_deeds.values()),
        "documents": list(seen_documents.values()),
    }


def get_decision_makers(
    session: Session,
    enterprise_number: str,
    *,
    limit: int = 100,
) -> list[DecisionMakerRow]:
    """Return party roles for matching deeds, excluding notaries."""

    normalized = normalize_enterprise_number(enterprise_number)
    deed_ids = (
        select(Deed.id)
        .join(Document, Deed.document_id == Document.id)
        .outerjoin(Company, Company.deed_id == Deed.id)
        .where(
            or_(
                enterprise_number_expression(Company.enterprise_number) == normalized,
                enterprise_number_expression(Deed.extracted_enterprise_number) == normalized,
                enterprise_number_expression(Deed.source_enterprise_number) == normalized,
                enterprise_number_expression(Document.source_enterprise_number) == normalized,
            )
        )
    )
    stmt = (
        select(PartyRole, Deed, Document)
        .join(Deed, PartyRole.deed_id == Deed.id)
        .join(Document, Deed.document_id == Document.id)
        .where(PartyRole.deed_id.in_(deed_ids), PartyRole.party_type != "notary")
        .order_by(Document.file_name, Deed.publication_reference, PartyRole.name)
        .limit(limit)
    )
    return [DecisionMakerRow(*row) for row in session.execute(stmt)]


def get_document_with_children(session: Session, document_id) -> Document | None:
    """Fetch one document with deeds, companies, and party roles preloaded."""

    stmt = (
        select(Document)
        .options(
            selectinload(Document.deeds).selectinload(Deed.companies),
            selectinload(Document.deeds).selectinload(Deed.party_roles),
        )
        .where(Document.id == document_id)
    )
    return session.scalar(stmt)
