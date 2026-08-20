"""Read-only SQL guard for the AI agent.

The agent lets a user ask questions in natural language, and an LLM turns those
into SQL. That SQL is untrusted: a bad prompt, a jailbreak, or an honest mistake
could produce a statement that writes to or destroys the database. This guard is
the hard boundary. Every query the agent runs passes through `assert_read_only`
first, and anything that is not a single, plain SELECT/WITH read is rejected.

Kept deliberately separate from the MCP server so it can be unit-tested on its
own, with no database and no MCP runtime. The guard is the security-critical part,
so it is the part that is tested most.
"""

from __future__ import annotations

import re


# Statement types that read data and nothing else. Anything not starting with one
# of these (after stripping) is rejected outright.
ALLOWED_PREFIXES = ("select", "with")

# Whole-word tokens that must never appear in a read-only query. Even inside a
# SELECT, these signal an attempt to change data or schema.
FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "copy", "call", "merge", "replace",
    "commit", "rollback", "vacuum", "reindex", "attach",
)

# Only these tables may be referenced. A whitelist means a crafted query cannot
# read Postgres system catalogs (pg_*), other schemas, or credentials tables.
ALLOWED_TABLES = frozenset(
    {"documents", "deeds", "companies", "party_roles", "extraction_runs"}
)


def assert_read_only(sql: str) -> str:
    """Return the cleaned SQL if it is a safe read, otherwise raise ValueError.

    The checks are layered so no single trick gets through:
    1. non-empty
    2. no SQL comments (a common way to hide a second statement or bypass a filter)
    3. exactly one statement (no stacked `SELECT ...; DROP ...`)
    4. starts with SELECT or WITH
    5. contains no data- or schema-changing keyword
    """

    if sql is None or not sql.strip():
        raise ValueError("Empty query.")

    cleaned = sql.strip()

    # Reject comments outright. `--` and `/* */` are the usual way to smuggle a
    # second statement or comment out part of a guard, and legitimate agent
    # queries never need them.
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise ValueError("Comments are not allowed in agent queries.")

    # Allow one trailing semicolon, but reject anything that stacks statements.
    without_trailing = cleaned.rstrip(";").strip()
    if ";" in without_trailing:
        raise ValueError("Multiple statements are not allowed.")

    lowered = without_trailing.lower()
    if not lowered.startswith(ALLOWED_PREFIXES):
        raise ValueError("Only SELECT or WITH queries are allowed.")

    # Whole-word match so column names like 'created_at' never trip 'create'.
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise ValueError(f"Forbidden keyword in query: {keyword}.")

    return without_trailing


def assert_allowed_tables(sql: str) -> str:
    """Reject queries that reference tables outside the whitelist.

    We look at identifiers that follow FROM or JOIN. Anything that is not one of
    the known deed tables (for example a `pg_` system catalog) is rejected.
    """

    for match in re.finditer(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", sql.lower()):
        table = match.group(1).split(".")[-1]  # ignore any schema qualifier
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Query references a table that is not allowed: {table}.")
    return sql


def validate_agent_sql(sql: str) -> str:
    """Full validation used by the agent: read-only plus table whitelist."""

    cleaned = assert_read_only(sql)
    assert_allowed_tables(cleaned)
    return cleaned
