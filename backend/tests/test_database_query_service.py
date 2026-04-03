import asyncio
from datetime import datetime, timezone

import pytest

from paper_agent.services.database_query import DatabaseQueryService, DatabaseQueryValidationError, DatabaseSchemaInspectionError


class FakeMappingsResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, object]]:
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeMappingsResult:
        return FakeMappingsResult(self._rows)


class FakeSession:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.executed_sql: str | None = None

    async def execute(self, statement) -> FakeExecuteResult:
        self.executed_sql = str(statement)
        return FakeExecuteResult(self.rows)


def test_describe_schema_lists_expected_tables() -> None:
    service = DatabaseQueryService(max_rows=25)
    expected_schema = {
        "dialect": "sqlite",
        "rules": [
            "Only read-only SQL is allowed.",
            "Only these tables may be queried: conferences, import_jobs, papers.",
            "SELECT * and table.* are not allowed; specify columns explicitly.",
            "Use SELECT statements for metadata and listing tasks.",
            "Results are capped to at most 25 rows.",
        ],
        "tables": [
            {"name": "conferences", "columns": [{"name": "id", "type": "VARCHAR(36)", "nullable": False}]},
            {"name": "papers", "columns": [{"name": "title", "type": "TEXT", "nullable": False}]},
        ],
    }

    class FakeSchemaSession:
        async def run_sync(self, fn):
            return expected_schema

    schema = asyncio.run(service.describe_schema(FakeSchemaSession()))  # type: ignore[arg-type]

    assert schema["dialect"] == "sqlite"
    assert [table["name"] for table in schema["tables"]] == ["conferences", "papers"]
    assert schema["rules"] == expected_schema["rules"]


def test_execute_readonly_sql_adds_limit_and_serializes_rows() -> None:
    service = DatabaseQueryService(max_rows=2)
    session = FakeSession(
        rows=[
            {
                "name": "USENIX Security",
                "year": 2025,
                "created_at": datetime(2026, 4, 4, 10, 30, tzinfo=timezone.utc),
            }
        ]
    )

    result = asyncio.run(
        service.execute_readonly_sql(
            session,  # type: ignore[arg-type]
            "SELECT name, year, created_at FROM conferences ORDER BY year DESC",
        )
    )

    assert session.executed_sql is not None
    assert "LIMIT 2" in session.executed_sql
    assert result.row_count == 1
    assert result.rows[0]["name"] == "USENIX Security"
    assert result.rows[0]["created_at"] == "2026-04-04T10:30:00+00:00"


def test_describe_schema_wraps_errors() -> None:
    service = DatabaseQueryService()

    class FailingSchemaSession:
        async def run_sync(self, fn):
            raise RuntimeError("boom")

    with pytest.raises(DatabaseSchemaInspectionError):
        asyncio.run(service.describe_schema(FailingSchemaSession()))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "sql, expected_message",
    [
        ("SELECT * FROM conferences", "SELECT \\* is not allowed"),
        ("SELECT conferences.* FROM conferences", "Wildcard column selection"),
        ("SELECT secret FROM users", "Only these tables may be queried"),
    ],
)
def test_execute_readonly_sql_rejects_disallowed_tables_and_wildcards(sql: str, expected_message: str) -> None:
    service = DatabaseQueryService()

    with pytest.raises(DatabaseQueryValidationError, match=expected_message):
        service._validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "DELETE FROM conferences",
        "UPDATE papers SET title = 'x'",
        "SELECT * FROM conferences; DROP TABLE conferences",
    ],
)
def test_execute_readonly_sql_rejects_non_select_queries(sql: str) -> None:
    service = DatabaseQueryService()

    with pytest.raises(DatabaseQueryValidationError):
        service._validate_sql(sql)
