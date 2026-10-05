"""PostgreSQL helpers: connect, run SQL files, and upsert DataFrames."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from src.config import SQL_DIR, get_warehouse_settings
from src.utils.errors import LoadError
from src.utils.logger import get_logger

log = get_logger("load.db")


def get_connection():
    """Open a connection using the settings from environment variables (.env)."""
    settings = get_warehouse_settings()
    try:
        # client_encoding: country names such as "Curaçao" and "Côte d'Ivoire" need UTF-8
        return psycopg2.connect(**settings, connect_timeout=10, client_encoding="utf8")
    except psycopg2.OperationalError as err:
        raise LoadError(f"Cannot connect to PostgreSQL at {settings['host']}:{settings['port']}: {err}") from err


def run_sql_file(conn, path: Path) -> None:
    """Run every statement in a .sql file."""
    with conn.cursor() as cur:
        cur.execute(Path(path).read_text(encoding="utf-8"))
    log.info("Ran %s", Path(path).name)


def _to_python(value):
    """psycopg2 understands Python values, not numpy/pandas ones (e.g. numpy.int64, pd.NA)."""
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def upsert_dataframe(conn, table: str, df: pd.DataFrame, key_columns: list[str]) -> int:
    """Insert rows; if a row with the same key already exists, update it instead.

    This is what makes reruns safe: loading the same data twice never creates duplicates.
    """
    columns = list(df.columns)
    update_columns = [c for c in columns if c not in key_columns]
    on_conflict = ("DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
                   if update_columns else "DO NOTHING")
    sql = (f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
           f"ON CONFLICT ({', '.join(key_columns)}) {on_conflict}")
    rows = [tuple(_to_python(v) for v in row) for row in df.itertuples(index=False, name=None)]
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=5000)
    log.info("Upserted %d rows into %s", len(rows), table)
    return len(rows)


def fetch_value(conn, sql: str, params: tuple | None = None):
    """Run a query that returns one value (e.g. a COUNT)."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def create_schema() -> None:
    """Create the warehouse tables (safe to run again)."""
    conn = get_connection()
    try:
        with conn:  # commits on success, rolls back on error
            run_sql_file(conn, SQL_DIR / "01_schema.sql")
    finally:
        conn.close()


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    create_schema()
    print("Schema is ready.")
