"""Pydantic models for Gemini extraction output.

These models are the contract between the LLM and the rest of the pipeline.
They are intentionally separate from API response models and SQLAlchemy models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


LanguageCode = Literal["nl", "fr", "de", "mixed", "unknown"]
PartyType = Literal["person", "company", "notary", "association", "unknown"]
DocumentSourceType = Literal["scan", "searchable_pdf", "mixed", "unknown"]


class PartyRoleExtraction(BaseModel):
    """A person, company, notary, or association mentioned in a deed."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    party_type: PartyType | None = Field(
        default=None,
        description="person, company, notary, association, or unknown",
    )
    role: str | None = None
    address: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_context: str | None = None


class CompanyExtraction(BaseModel):
    """Company-level facts extracted from one deed notice."""

    model_config = ConfigDict(extra="forbid")

    enterprise_number: str | None = None
    company_name: str | None = None
    legal_form: str | None = None
    registered_office_address: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None
    corporate_purpose: str | None = None
    capital_amount: float | None = None
    capital_currency: str | None = None

    @field_validator("enterprise_number")
    @classmethod
    def normalize_enterprise_number(cls, value: str | None) -> str | None:
        """Trim whitespace while preserving the source formatting."""

        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DeedExtraction(BaseModel):
    """One Gazette notice/deed extracted from a PDF page or document."""

    model_config = ConfigDict(extra="forbid")

    extracted_enterprise_number: str | None = Field(
        default=None,
        description="Enterprise number explicitly stated for this deed notice, when present.",
    )
    deed_type: str | None = None
    deed_date: str | None = None
    publication_date: str | None = None
    publication_reference: str | None = Field(
        default=None,
        description="Printed Gazette notice reference such as 'N. 970916 — 333'.",
    )
    form_reference: str | None = Field(
        default=None,
        description="Explicit form identifier such as Form I, Form II, Volet B, Luik B when present.",
    )
    language: LanguageCode | None = None
    summary: str | None = None
    companies: list[CompanyExtraction] = Field(default_factory=list)
    party_roles: list[PartyRoleExtraction] = Field(default_factory=list)

    @field_validator("extracted_enterprise_number")
    @classmethod
    def normalize_extracted_enterprise_number(cls, value: str | None) -> str | None:
        """Trim whitespace and convert empty strings to null."""

        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class GeminiExtraction(BaseModel):
    """The exact top-level JSON shape Gemini is allowed to return."""

    model_config = ConfigDict(extra="forbid")

    deeds: list[DeedExtraction] = Field(default_factory=list)


class DocumentExtraction(BaseModel):
    """Validated artifact written to outputs/extractions/*.json."""

    model_config = ConfigDict(extra="forbid")

    source_file: str
    page_count: int
    ocr_used: bool
    source_type: DocumentSourceType = "unknown"
    deeds: list[DeedExtraction] = Field(default_factory=list)
