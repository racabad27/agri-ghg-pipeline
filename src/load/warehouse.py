"""Load curated tables into PostgreSQL, then check that the database matches the files."""
from __future__ import annotations

import pandas as pd

from src.config import CURATED_DIR, SQL_DIR
from src.load.db import fetch_value, get_connection, run_sql_file, upsert_dataframe
from src.utils.files import new_batch_id, utc_now
from src.utils.logger import get_logger
from src.validation.checks import expect_true, run_checks

log = get_logger("load.warehouse")

GASES = pd.DataFrame({
    "gas_code": ["CO2", "CH4", "N2O"],
    "gas_name": ["Carbon dioxide", "Methane", "Nitrous oxide"],
    "gwp100_ar5": [1.0, 28.0, 265.0],
})

# table name -> (curated file, primary key)
FACT_TABLES = {
    "agri.fact_emissions": ("agri_emissions_by_gas", ["country_code", "gas_code", "year"]),
    "agri.fact_population": ("population", ["country_code", "year"]),
    "agri.agri_country_year": ("agri_country_year", ["country_code", "year"]),
    "agri.fact_emissions_by_activity": ("agri_emissions_by_activity", ["country_code", "activity_code", "year"]),
    "agri.edgar_vs_faostat": ("edgar_vs_faostat", ["country_code", "year"]),
}


def _read_curated(name: str) -> pd.DataFrame:
    df = pd.read_parquet(CURATED_DIR / f"{name}.parquet").rename(columns={"gas": "gas_code"})
    if name == "agri_emissions_by_activity":
        # activity names and groups are stored once, in dim_activity; the fact table keeps only the code
        df = df.drop(columns=["activity", "activity_group"])
    return df


def load_warehouse(batch_id: str | None = None) -> dict:
    """Upsert all curated tables in one transaction and write the load audit."""
    batch_id = batch_id or new_batch_id()
    loaded_at = utc_now()
    counts = {}
    conn = get_connection()
    try:
        with conn:  # one transaction: commit at the end, roll back on any error
            run_sql_file(conn, SQL_DIR / "01_schema.sql")
            counts["agri.dim_gas"] = (upsert_dataframe(conn, "agri.dim_gas", GASES, ["gas_code"]), 0)
            dim_country = _read_curated("dim_country")
            counts["agri.dim_country"] = (upsert_dataframe(conn, "agri.dim_country", dim_country, ["country_code"]), 0)
            dim_activity = _read_curated("dim_activity")
            counts["agri.dim_activity"] = (upsert_dataframe(conn, "agri.dim_activity", dim_activity, ["activity_code"]), 0)

            for table, (name, key) in FACT_TABLES.items():
                df = _read_curated(name).assign(batch_id=batch_id, loaded_at=loaded_at)
                upserted = upsert_dataframe(conn, table, df, key)
                with conn.cursor() as cur:  # remove rows this batch did not touch (stale data)
                    cur.execute(f"DELETE FROM {table} WHERE batch_id <> %s", (batch_id,))
                    deleted = cur.rowcount
                counts[table] = (upserted, deleted)

            with conn.cursor() as cur:
                for table, (upserted, deleted) in counts.items():
                    cur.execute("INSERT INTO agri.load_audit (batch_id, table_name, rows_upserted, rows_deleted)"
                                " VALUES (%s, %s, %s, %s)", (batch_id, table, upserted, deleted))
    finally:
        conn.close()

    for table, (upserted, deleted) in counts.items():
        log.info("%s: %d rows upserted, %d stale rows deleted", table, upserted, deleted)
    return {"batch_id": batch_id, **{t: c[0] for t, c in counts.items()}}


def check_warehouse() -> dict:
    """After loading: the database must match the curated files exactly."""
    results = []
    conn = get_connection()
    try:
        for table, (name, _key) in FACT_TABLES.items():
            expected = len(_read_curated(name))
            actual = fetch_value(conn, f"SELECT COUNT(*) FROM {table}")
            results.append(expect_true(f"row count {table} = curated file", actual == expected,
                                       f"database {actual:,} vs file {expected:,}"))

        latest_year = int(_read_curated("agri_country_year")["year"].max())
        file_total = float(_read_curated("agri_emissions_by_gas").query("year == @latest_year")
                           ["emissions_mt_co2eq"].sum())
        db_total = float(fetch_value(conn, "SELECT SUM(emissions_mt_co2eq) FROM agri.fact_emissions WHERE year = %s",
                                     (latest_year,)))
        results.append(expect_true(f"world total {latest_year} in database = curated file",
                                   abs(db_total - file_total) < 1e-6 * max(file_total, 1),
                                   f"database {db_total:,.3f} Mt vs file {file_total:,.3f} Mt"))

        orphans = fetch_value(conn, "SELECT COUNT(*) FROM agri.fact_emissions f "
                                    "LEFT JOIN agri.dim_country c USING (country_code) WHERE c.country_code IS NULL")
        results.append(expect_true("referential integrity: no emissions without a country", orphans == 0,
                                   f"{orphans} orphan rows"))
    finally:
        conn.close()
    return run_checks("warehouse", results)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(load_warehouse())
    check_warehouse()
