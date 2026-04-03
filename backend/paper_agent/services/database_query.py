import enum
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


FORBIDDEN_SQL_PATTERNS = (
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bdrop\b",
    r"\balter\b",
    r"\bcreate\b",
    r"\btruncate\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\bcopy\b",
    r"\bmerge\b",
    r"\bvacuum\b",
    r"\banalyze\b",
    r"\brefresh\b",
    r"\bcomment\b",
    r"\bexecute\b",
    r"\bcall\b",
    r"\bdo\b",
)

ALLOWED_TABLES = frozenset({"conferences", "papers", "import_jobs"})
TABLE_REFERENCE_PATTERN = re.compile(
    r"\b(?:from|join)\s+([a-zA-Z_][\w\.]*)(?:\s+(?:as\s+)?[a-zA-Z_][\w]*)?",
    flags=re.IGNORECASE,
)
SELECT_STAR_PATTERN = re.compile(r"\bselect\s+(?:distinct\s+)?\*", flags=re.IGNORECASE)
TABLE_STAR_PATTERN = re.compile(r"\b[a-zA-Z_][\w]*\.\*", flags=re.IGNORECASE)


@dataclass(slots=True)
class QueryResult:
    sql: str
    row_count: int
    rows: list[dict[str, object]]
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "sql": self.sql,
            "row_count": self.row_count,
            "rows": self.rows,
            "truncated": self.truncated,
        }


class DatabaseQueryValidationError(ValueError):
    pass


class DatabaseSchemaInspectionError(RuntimeError):
    pass


class DatabaseQueryService:
    def __init__(self, max_rows: int = 100, allowed_tables: set[str] | None = None) -> None:
        self.max_rows = max_rows
        self.allowed_tables = frozenset(allowed_tables or ALLOWED_TABLES)

    async def describe_schema(self, session: AsyncSession) -> dict[str, object]:
        try:
            return await session.run_sync(self._inspect_schema_sync)
        except Exception as error:  # pragma: no cover - exercised via wrapper tests
            raise DatabaseSchemaInspectionError(str(error)) from error

    async def execute_readonly_sql(self, session: AsyncSession, sql: str) -> QueryResult:
        normalized_sql = self._validate_sql(sql)
        limited_sql = self._ensure_limit(normalized_sql)
        result = await session.execute(text(limited_sql))
        rows = result.mappings().all()
        serialized_rows = [self._serialize_row(dict(row)) for row in rows]
        truncated = len(serialized_rows) >= self.max_rows and " limit " not in normalized_sql.lower()
        return QueryResult(
            sql=limited_sql,
            row_count=len(serialized_rows),
            rows=serialized_rows,
            truncated=truncated,
        )

    def _validate_sql(self, sql: str) -> str:
        normalized_sql = sql.strip()
        if not normalized_sql:
            raise DatabaseQueryValidationError("SQL query cannot be empty.")

        if normalized_sql.endswith(";"):
            normalized_sql = normalized_sql[:-1].strip()
        if ";" in normalized_sql:
            raise DatabaseQueryValidationError("Only a single SQL statement is allowed.")

        lowered = normalized_sql.lower()
        if not (lowered.startswith("select") or lowered.startswith("with")):
            raise DatabaseQueryValidationError("Only SELECT queries are allowed.")

        for pattern in FORBIDDEN_SQL_PATTERNS:
            if re.search(pattern, lowered):
                raise DatabaseQueryValidationError("Only read-only SQL queries are allowed.")

        self._validate_select_columns(normalized_sql)
        self._validate_table_references(normalized_sql)

        return normalized_sql

    def _ensure_limit(self, sql: str) -> str:
        if re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE):
            return sql
        return f"{sql}\nLIMIT {self.max_rows}"

    def _serialize_row(self, row: dict[str, object]) -> dict[str, object]:
        return {key: self._serialize_value(value) for key, value in row.items()}

    def _serialize_value(self, value: object) -> object:
        if isinstance(value, enum.Enum):
            return value.value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    def _inspect_schema_sync(self, sync_session) -> dict[str, object]:
        bind = sync_session.get_bind()
        inspector = inspect(bind)
        table_names = sorted(inspector.get_table_names())
        tables: list[dict[str, object]] = []

        for table_name in table_names:
            columns: list[dict[str, object]] = []
            for column in inspector.get_columns(table_name):
                columns.append(
                    {
                        "name": str(column["name"]),
                        "type": self._format_sql_type(column.get("type")),
                        "nullable": bool(column.get("nullable", True)),
                    }
                )

            tables.append(
                {
                    "name": table_name,
                    "columns": columns,
                }
            )

        return {
            "dialect": bind.dialect.name,
            "rules": [
                "Only read-only SQL is allowed.",
                f"Only these tables may be queried: {', '.join(sorted(self.allowed_tables))}.",
                "SELECT * and table.* are not allowed; specify columns explicitly.",
                "Use SELECT statements for metadata and listing tasks.",
                f"Results are capped to at most {self.max_rows} rows.",
            ],
            "tables": tables,
        }

    def _format_sql_type(self, sql_type: Any) -> str:
        if sql_type is None:
            return "unknown"
        return str(sql_type)

    def _validate_table_references(self, sql: str) -> None:
        referenced_tables = {
            self._normalize_table_name(match.group(1))
            for match in TABLE_REFERENCE_PATTERN.finditer(sql)
        }
        disallowed_tables = sorted(table for table in referenced_tables if table not in self.allowed_tables)
        if disallowed_tables:
            raise DatabaseQueryValidationError(
                f"Only these tables may be queried: {', '.join(sorted(self.allowed_tables))}. "
                f"Disallowed tables: {', '.join(disallowed_tables)}."
            )

    def _validate_select_columns(self, sql: str) -> None:
        lowered = sql.lower()
        if SELECT_STAR_PATTERN.search(lowered):
            raise DatabaseQueryValidationError("SELECT * is not allowed. Specify columns explicitly.")

        sanitized = re.sub(r"count\s*\(\s*\*\s*\)", "count(__all__)", lowered, flags=re.IGNORECASE)
        if TABLE_STAR_PATTERN.search(sanitized):
            raise DatabaseQueryValidationError("Wildcard column selection like table.* is not allowed.")

    def _normalize_table_name(self, table_name: str) -> str:
        return table_name.split(".")[-1].strip('"').lower()
