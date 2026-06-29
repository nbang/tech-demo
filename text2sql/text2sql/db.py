"""Postgres connectivity: schema introspection (DDL) and query execution."""

from __future__ import annotations

import datetime as _dt
import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import settings

# Schemas we never introspect.
_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


@dataclass
class Column:
    name: str
    data_type: str
    nullable: bool
    default: str | None
    comment: str | None


@dataclass
class Table:
    schema: str
    name: str
    comment: str | None = None
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[dict[str, str]] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"

    def to_document(self) -> str:
        """Human + LLM readable description of the table — this is what we embed and prompt with."""
        lines = [f"Table: {self.qualified}"]
        if self.comment:
            lines.append(f"Description: {self.comment}")
        lines.append("Columns:")
        for c in self.columns:
            parts = [f"  - {c.name} {c.data_type}"]
            if not c.nullable:
                parts.append("NOT NULL")
            if c.default:
                parts.append(f"DEFAULT {c.default}")
            line = " ".join(parts)
            if c.comment:
                line += f"  -- {c.comment}"
            lines.append(line)
        if self.primary_key:
            lines.append(f"Primary key: ({', '.join(self.primary_key)})")
        if self.foreign_keys:
            lines.append("Foreign keys:")
            for fk in self.foreign_keys:
                lines.append(
                    f"  - {fk['column']} -> {fk['ref_table']}({fk['ref_column']})"
                )
        if self.indexes:
            lines.append("Indexes:")
            for idx in self.indexes:
                lines.append(f"  - {idx}")
        return "\n".join(lines)

    def to_ddl(self) -> str:
        """Emit a CREATE TABLE statement — the format text-to-SQL models (e.g. sqlcoder) expect."""
        defs: list[tuple[str, str]] = []  # (definition, inline-comment)
        for c in self.columns:
            d = f"{c.name} {c.data_type}"
            if not c.nullable:
                d += " NOT NULL"
            defs.append((d, f" -- {c.comment}" if c.comment else ""))
        if self.primary_key:
            defs.append((f"PRIMARY KEY ({', '.join(self.primary_key)})", ""))
        for fk in self.foreign_keys:
            defs.append(
                (f"FOREIGN KEY ({fk['column']}) REFERENCES {fk['ref_table']}({fk['ref_column']})", "")
            )
        lines = []
        for i, (d, comment) in enumerate(defs):
            sep = "," if i < len(defs) - 1 else ""
            lines.append(f"  {d}{sep}{comment}")
        tbl_comment = f" -- {self.comment}" if self.comment else ""
        return f"CREATE TABLE {self.qualified} ({tbl_comment}\n" + "\n".join(lines) + "\n);"


def _connect(connection_string: str) -> psycopg.Connection:
    return psycopg.connect(connection_string, row_factory=dict_row, connect_timeout=15)


def introspect(connection_string: str) -> list[Table]:
    """Read the live schema and return one Table per BASE TABLE."""
    sys_list = "', '".join(_SYSTEM_SCHEMAS)
    tables: dict[str, Table] = {}

    with _connect(connection_string) as conn, conn.cursor() as cur:
        # Tables + table comments.
        cur.execute(
            f"""
            SELECT n.nspname AS schema, c.relname AS name,
                   obj_description(c.oid) AS comment
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname NOT IN ('{sys_list}')
            ORDER BY 1, 2
            """
        )
        for r in cur.fetchall():
            t = Table(schema=r["schema"], name=r["name"], comment=r["comment"])
            tables[t.qualified] = t

        # Columns + column comments + types.
        cur.execute(
            f"""
            SELECT n.nspname AS schema, c.relname AS table, a.attname AS column,
                   pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                   NOT a.attnotnull AS nullable,
                   pg_get_expr(ad.adbin, ad.adrelid) AS default,
                   col_description(c.oid, a.attnum) AS comment,
                   a.attnum AS ordinal
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_catalog.pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
            WHERE c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
              AND n.nspname NOT IN ('{sys_list}')
            ORDER BY n.nspname, c.relname, a.attnum
            """
        )
        for r in cur.fetchall():
            key = f"{r['schema']}.{r['table']}"
            if key in tables:
                tables[key].columns.append(
                    Column(
                        name=r["column"],
                        data_type=r["data_type"],
                        nullable=r["nullable"],
                        default=r["default"],
                        comment=r["comment"],
                    )
                )

        # Primary keys and foreign keys.
        cur.execute(
            f"""
            SELECT n.nspname AS schema, c.relname AS table, con.contype AS type,
                   con.conname AS name,
                   pg_get_constraintdef(con.oid) AS definition
            FROM pg_catalog.pg_constraint con
            JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE con.contype IN ('p', 'f') AND n.nspname NOT IN ('{sys_list}')
            """
        )
        for r in cur.fetchall():
            key = f"{r['schema']}.{r['table']}"
            t = tables.get(key)
            if not t:
                continue
            definition = r["definition"]
            if r["type"] == "p":  # PRIMARY KEY (a, b)
                inner = definition[definition.find("(") + 1 : definition.rfind(")")]
                t.primary_key = [c.strip() for c in inner.split(",")]
            elif r["type"] == "f":  # FOREIGN KEY (col) REFERENCES tbl(col)
                t.foreign_keys.append(_parse_fk(definition))

        # Indexes (skip the ones backing PK/unique constraints already shown).
        cur.execute(
            f"""
            SELECT schemaname AS schema, tablename AS table, indexdef
            FROM pg_indexes
            WHERE schemaname NOT IN ('{sys_list}')
            """
        )
        for r in cur.fetchall():
            key = f"{r['schema']}.{r['table']}"
            t = tables.get(key)
            if t:
                # Compact form: drop the verbose "CREATE INDEX ... ON ... USING" prefix.
                t.indexes.append(r["indexdef"])

    return list(tables.values())


def _parse_fk(definition: str) -> dict[str, str]:
    """Parse 'FOREIGN KEY (col) REFERENCES schema.tbl(refcol) ...' into structured parts."""
    col = definition[definition.find("(") + 1 : definition.find(")")].strip()
    after = definition[definition.find("REFERENCES") + len("REFERENCES") :].strip()
    ref_table = after[: after.find("(")].strip()
    ref_column = after[after.find("(") + 1 : after.find(")")].strip()
    return {"column": col, "ref_table": ref_table, "ref_column": ref_column}


def _json_safe(value: Any) -> Any:
    if isinstance(value, (decimal.Decimal,)):
        return float(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, (_dt.timedelta,)):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    return value


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    rowcount: int
    truncated: bool


def run_query(connection_string: str, sql: str) -> QueryResult:
    """Execute SQL and return results. Honors TEXT2SQL_READONLY and TEXT2SQL_MAX_ROWS."""
    with _connect(connection_string) as conn:
        if settings.read_only:
            conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                # Non-row-returning statement (INSERT/UPDATE/DDL/...).
                conn.commit()
                return QueryResult(columns=[], rows=[], rowcount=cur.rowcount, truncated=False)
            columns = [d.name for d in cur.description]
            fetched = cur.fetchmany(settings.max_rows + 1)
            truncated = len(fetched) > settings.max_rows
            rows = [
                [_json_safe(v) for v in row.values()]
                for row in fetched[: settings.max_rows]
            ]
            conn.commit()
            return QueryResult(
                columns=columns,
                rows=rows,
                rowcount=len(rows),
                truncated=truncated,
            )
