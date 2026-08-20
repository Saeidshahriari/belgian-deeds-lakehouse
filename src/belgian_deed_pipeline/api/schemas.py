"""Pydantic response models for the FastAPI app.

These models describe HTTP responses only. They are separate from the Gemini
extraction schema because API output and LLM input/output have different needs.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StatsResponse(BaseModel):
    """Counts returned by GET /stats."""

    documents: int
    deeds: int
    companies: int
    party_roles: int


class DocumentResponse(BaseModel):
    """Document fields exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_enterprise_number: str | None
    file_name: str
    file_path: str
    page_count: int
    source_type: str
    ocr_used: bool
    ocr_status: str
    ocr_text_path: str | None
    processing_status: str


class DeedResponse(BaseModel):
    """Deed fields exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    source_enterprise_number: str | None
    extracted_enterprise_number: str | None
    deed_type: str | None
    deed_type_normalized: str | None
    deed_date: str | None
    publication_date: str | None
    publication_reference: str | None
    form_reference: str | None
    language: str | None
    summary: str | None


class CompanyResponse(BaseModel):
    """Company fields exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deed_id: UUID
    enterprise_number: str | None
    company_name: str | None
    legal_form: str | None
    registered_office_address: str | None
    postal_code: str | None
    city: str | None
    country: str | None
    corporate_purpose: str | None
    capital_amount: Decimal | None
    capital_currency: str | None


class PartyRoleResponse(BaseModel):
    """Party-role fields exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deed_id: UUID
    name: str | None
    party_type: str | None
    role: str | None
    address: str | None
    start_date: str | None
    end_date: str | None
    confidence: Decimal | None
    raw_context: str | None


class CompanySearchResult(BaseModel):
    """One company search hit with context."""

    company: CompanyResponse
    deed: DeedResponse
    document: DocumentResponse


class CompanyProfileResponse(BaseModel):
    """Full company profile returned by enterprise-number lookup."""

    enterprise_number: str
    companies: list[CompanyResponse]
    deeds: list[DeedResponse]
    documents: list[DocumentResponse]


class DecisionMakerResponse(BaseModel):
    """One decision-maker/party-role hit with context."""

    party_role: PartyRoleResponse
    deed: DeedResponse
    document: DocumentResponse
