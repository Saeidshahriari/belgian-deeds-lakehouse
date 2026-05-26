"""Initial PostgreSQL schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial relational schema and supporting indexes."""

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_enterprise_number", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("ocr_used", sa.Boolean(), nullable=False),
        sa.Column("ocr_status", sa.Text(), nullable=False),
        sa.Column("ocr_text_path", sa.Text(), nullable=True),
        sa.Column("processing_status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash"),
    )
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])
    op.create_index("ix_documents_source_enterprise_number", "documents", ["source_enterprise_number"])

    op.create_table(
        "deeds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_enterprise_number", sa.Text(), nullable=True),
        sa.Column("extracted_enterprise_number", sa.Text(), nullable=True),
        sa.Column("deed_type", sa.Text(), nullable=True),
        sa.Column("deed_type_normalized", sa.Text(), nullable=True),
        sa.Column("deed_date", sa.Text(), nullable=True),
        sa.Column("publication_date", sa.Text(), nullable=True),
        sa.Column("publication_reference", sa.Text(), nullable=True),
        sa.Column("form_reference", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deeds_document_id", "deeds", ["document_id"])
    op.create_index("ix_deeds_source_enterprise_number", "deeds", ["source_enterprise_number"])
    op.create_index("ix_deeds_publication_reference", "deeds", ["publication_reference"])
    op.create_index("ix_deeds_deed_type_normalized", "deeds", ["deed_type_normalized"])
    op.create_index("ix_deeds_language", "deeds", ["language"])

    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deed_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enterprise_number", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("legal_form", sa.Text(), nullable=True),
        sa.Column("registered_office_address", sa.Text(), nullable=True),
        sa.Column("postal_code", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("corporate_purpose", sa.Text(), nullable=True),
        sa.Column("capital_amount", sa.Numeric(), nullable=True),
        sa.Column("capital_currency", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["deed_id"], ["deeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_deed_id", "companies", ["deed_id"])
    op.create_index("ix_companies_enterprise_number", "companies", ["enterprise_number"])
    op.create_index("ix_companies_company_name", "companies", ["company_name"])

    op.create_table(
        "party_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deed_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("party_type", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Text(), nullable=True),
        sa.Column("end_date", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        sa.Column("raw_context", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["deed_id"], ["deeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_party_roles_deed_id", "party_roles", ["deed_id"])
    op.create_index("ix_party_roles_name", "party_roles", ["name"])

    op.create_table(
        "extraction_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("ocr_used", sa.Boolean(), nullable=False),
        sa.Column("raw_gemini_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extraction_runs_document_id", "extraction_runs", ["document_id"])


def downgrade() -> None:
    """Drop tables in reverse dependency order."""

    op.drop_index("ix_extraction_runs_document_id", table_name="extraction_runs")
    op.drop_table("extraction_runs")

    op.drop_index("ix_party_roles_name", table_name="party_roles")
    op.drop_index("ix_party_roles_deed_id", table_name="party_roles")
    op.drop_table("party_roles")

    op.drop_index("ix_companies_company_name", table_name="companies")
    op.drop_index("ix_companies_enterprise_number", table_name="companies")
    op.drop_index("ix_companies_deed_id", table_name="companies")
    op.drop_table("companies")

    op.drop_index("ix_deeds_language", table_name="deeds")
    op.drop_index("ix_deeds_deed_type_normalized", table_name="deeds")
    op.drop_index("ix_deeds_publication_reference", table_name="deeds")
    op.drop_index("ix_deeds_source_enterprise_number", table_name="deeds")
    op.drop_index("ix_deeds_document_id", table_name="deeds")
    op.drop_table("deeds")

    op.drop_index("ix_documents_source_enterprise_number", table_name="documents")
    op.drop_index("ix_documents_file_hash", table_name="documents")
    op.drop_table("documents")
