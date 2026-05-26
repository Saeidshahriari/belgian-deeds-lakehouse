"""SQLAlchemy ORM models for the PostgreSQL schema.

The tables mirror the data shape discovered during the 50-PDF extraction:
documents contain one or more deeds, deeds contain company mentions and party
roles, and extraction_runs records the validated LLM output for auditability.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class used by Alembic to discover all ORM tables."""

    pass


class Document(Base):
    """One source PDF and deterministic processing metadata."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_file_hash", "file_hash"),
        Index("ix_documents_source_enterprise_number", "source_enterprise_number"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_enterprise_number: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    ocr_used: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ocr_status: Mapped[str] = mapped_column(Text, nullable=False)
    ocr_text_path: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    deeds: Mapped[list[Deed]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    extraction_runs: Mapped[list[ExtractionRun]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class Deed(Base):
    """One Gazette notice/deed extracted from a document."""

    __tablename__ = "deeds"
    __table_args__ = (
        Index("ix_deeds_document_id", "document_id"),
        Index("ix_deeds_source_enterprise_number", "source_enterprise_number"),
        Index("ix_deeds_publication_reference", "publication_reference"),
        Index("ix_deeds_deed_type_normalized", "deed_type_normalized"),
        Index("ix_deeds_language", "language"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_enterprise_number: Mapped[str | None] = mapped_column(Text)
    extracted_enterprise_number: Mapped[str | None] = mapped_column(Text)
    deed_type: Mapped[str | None] = mapped_column(Text)
    deed_type_normalized: Mapped[str | None] = mapped_column(Text)
    deed_date: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[str | None] = mapped_column(Text)
    publication_reference: Mapped[str | None] = mapped_column(Text)
    form_reference: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document: Mapped[Document] = relationship(back_populates="deeds")
    companies: Mapped[list[Company]] = relationship(
        back_populates="deed",
        cascade="all, delete-orphan",
    )
    party_roles: Mapped[list[PartyRole]] = relationship(
        back_populates="deed",
        cascade="all, delete-orphan",
    )


class Company(Base):
    """A company mention inside a deed notice."""

    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_deed_id", "deed_id"),
        Index("ix_companies_enterprise_number", "enterprise_number"),
        Index("ix_companies_company_name", "company_name"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    deed_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("deeds.id", ondelete="CASCADE"),
        nullable=False,
    )
    enterprise_number: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str | None] = mapped_column(Text)
    legal_form: Mapped[str | None] = mapped_column(Text)
    registered_office_address: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    corporate_purpose: Mapped[str | None] = mapped_column(Text)
    capital_amount: Mapped[Decimal | None] = mapped_column(Numeric)
    capital_currency: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    deed: Mapped[Deed] = relationship(back_populates="companies")


class PartyRole(Base):
    """A person/company/notary/association role mentioned in a deed."""

    __tablename__ = "party_roles"
    __table_args__ = (
        Index("ix_party_roles_deed_id", "deed_id"),
        Index("ix_party_roles_name", "name"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    deed_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("deeds.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(Text)
    party_type: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[str | None] = mapped_column(Text)
    end_date: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    raw_context: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    deed: Mapped[Deed] = relationship(back_populates="party_roles")


class ExtractionRun(Base):
    """Audit record for the model output used to create database rows."""

    __tablename__ = "extraction_runs"
    __table_args__ = (Index("ix_extraction_runs_document_id", "document_id"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    ocr_used: Mapped[bool] = mapped_column(Boolean, nullable=False)
    raw_gemini_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document: Mapped[Document] = relationship(back_populates="extraction_runs")
