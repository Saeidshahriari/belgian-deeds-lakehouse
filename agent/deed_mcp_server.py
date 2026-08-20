"""MCP server: a read-only AI agent over the Belgian deed database.

This exposes the loaded deed data to an AI assistant (Claude, or any MCP client)
so a user can ask questions in plain language — "which companies have capital over
100k?", "who are the directors of enterprise 0458279072?" — and the assistant
answers by calling these tools instead of guessing.

Two safety properties matter here, because the caller is an LLM:

1. Every structured tool reuses the same query functions the CLI and the FastAPI
   app use (`belgian_deed_pipeline.db.queries`). There is no second, weaker copy
   of the SQL.

2. The one free-form tool, `run_read_only_sql`, sends the SQL through
   `agent.sql_guard.validate_agent_sql` first. Only a single plain SELECT/WITH
   against the whitelisted deed tables can run. Anything that writes, drops,
   stacks statements, hides behind a comment, or touches a system catalog is
   rejected before it reaches the database.

Run it:  python agent/deed_mcp_server.py
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import text

from agent.sql_guard import validate_agent_sql
from belgian_deed_pipeline.config import load_database_url
from belgian_deed_pipeline.db import queries
from belgian_deed_pipeline.db.session import make_session_factory


mcp = FastMCP("belgian-deed-agent")

# One session factory for the whole server. The agent is read-only, so a simple
# shared factory is enough; each tool opens and closes its own session.
_session_factory = make_session_factory(load_database_url())


@mcp.tool()
def get_database_stats() -> dict[str, int]:
    """Return row counts for documents, deeds, companies, and party roles."""

    with _session_factory() as session:
        return queries.get_stats(session)


@mcp.tool()
def search_companies(name: str, limit: int = 25) -> list[dict[str, Any]]:
    """Find companies whose name contains the given text (case-insensitive)."""

    with _session_factory() as session:
        rows = queries.search_companies_by_name(session, name, limit=limit)
        return [
            {
                "company_name": row.company.company_name,
                "legal_form": row.company.legal_form,
                "capital_amount": _decimal_to_float(row.company.capital_amount),
                "capital_currency": row.company.capital_currency,
                "deed_type": row.deed.deed_type,
                "source_file": row.document.file_name,
            }
            for row in rows
        ]


@mcp.tool()
def get_company_profile(enterprise_number: str) -> dict[str, Any] | None:
    """Return all deeds, companies, and documents for one enterprise number."""

    with _session_factory() as session:
        profile = queries.get_company_profile(session, enterprise_number)
        if profile is None:
            return None
        return {
            "enterprise_number": profile["enterprise_number"],
            "companies": [c.company_name for c in profile["companies"]],
            "deed_count": len(profile["deeds"]),
            "document_count": len(profile["documents"]),
        }


@mcp.tool()
def get_decision_makers(enterprise_number: str, limit: int = 100) -> list[dict[str, Any]]:
    """Return founders/directors/signatories for a company, excluding notaries."""

    with _session_factory() as session:
        rows = queries.get_decision_makers(session, enterprise_number, limit=limit)
        return [
            {
                "name": row.party_role.name,
                "role": row.party_role.role,
                "party_type": row.party_role.party_type,
                "deed_type": row.deed.deed_type,
                "source_file": row.document.file_name,
            }
            for row in rows
        ]


@mcp.tool()
def run_read_only_sql(sql: str, limit: int = 200) -> list[dict[str, Any]]:
    """Run one read-only SELECT against the deed tables and return the rows.

    The SQL is validated by the read-only guard first: only a single SELECT/WITH
    against the whitelisted deed tables is allowed. A hard row cap is applied so a
    broad query cannot return the whole database.
    """

    safe_sql = validate_agent_sql(sql)
    with _session_factory() as session:
        result = session.execute(text(safe_sql))
        rows = result.mappings().all()
        return [dict(row) for row in rows[:limit]]


def _decimal_to_float(value: Any) -> float | None:
    """Convert Decimal capital amounts to float for JSON-friendly output."""

    return float(value) if value is not None else None


if __name__ == "__main__":
    # Runs over stdio, the transport MCP clients such as Claude Desktop use.
    mcp.run()
