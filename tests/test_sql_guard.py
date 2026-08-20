"""Tests for the agent's read-only SQL guard.

The guard is the security boundary between an LLM's generated SQL and the
database, so it is tested directly and thoroughly.
"""

import pytest

from agent.sql_guard import (
    assert_allowed_tables,
    assert_read_only,
    validate_agent_sql,
)


def test_plain_select_is_allowed() -> None:
    sql = "SELECT company_name FROM companies WHERE capital_amount > 100000"
    assert assert_read_only(sql) == sql


def test_with_cte_is_allowed() -> None:
    sql = "WITH t AS (SELECT id FROM deeds) SELECT * FROM t"
    assert assert_read_only(sql).startswith("WITH")


def test_trailing_semicolon_is_tolerated() -> None:
    sql = "SELECT 1 FROM documents;"
    assert assert_read_only(sql) == "SELECT 1 FROM documents"


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM companies",
        "DROP TABLE deeds",
        "UPDATE companies SET company_name = 'x'",
        "INSERT INTO deeds (id) VALUES ('x')",
        "TRUNCATE documents",
        "ALTER TABLE deeds ADD COLUMN x TEXT",
    ],
)
def test_write_statements_are_rejected(sql: str) -> None:
    with pytest.raises(ValueError):
        assert_read_only(sql)


def test_stacked_statements_are_rejected() -> None:
    with pytest.raises(ValueError):
        assert_read_only("SELECT 1 FROM documents; DROP TABLE documents")


def test_comment_bypass_is_rejected() -> None:
    # A classic trick: hide a second statement behind a comment.
    with pytest.raises(ValueError):
        assert_read_only("SELECT 1 /* */ ; DROP TABLE documents")


def test_column_named_like_keyword_is_allowed() -> None:
    # 'created_at' must not trip the 'create' keyword check.
    sql = "SELECT created_at FROM documents"
    assert assert_read_only(sql) == sql


def test_system_catalog_table_is_rejected() -> None:
    sql = "SELECT * FROM pg_shadow"
    with pytest.raises(ValueError):
        assert_allowed_tables(sql)


def test_full_validation_accepts_real_query() -> None:
    sql = (
        "SELECT c.company_name, c.capital_amount "
        "FROM companies c JOIN deeds d ON d.id = c.deed_id "
        "WHERE c.capital_amount > 100000"
    )
    assert validate_agent_sql(sql).startswith("SELECT")
