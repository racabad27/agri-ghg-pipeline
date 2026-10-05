"""Transform (raw -> staging): tidy the EDGAR sheet and save it as partitioned Parquet.

The EDGAR sheet is "wide": one row per substance, sector and country, and one column
per year (1970 ... 2025). We turn it "long": one row per country, sector, gas and year.

Output: data/staging/edgar/sector_key=<sector>/...parquet  (one folder per sector)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import STAGING_DIR, get_settings
from src.extract.edgar import edgar_raw_path
from src.utils.files import reset_dir
from src.utils.logger import get_logger

log = get_logger("transform.edgar")

ID_COLUMNS = ["Substance", "Sector", "EDGAR Country Code", "Country"]
STAGING_COLUMNS = [
    "country_code", "country_name", "country_type", "sector", "sector_key",
    "substance", "gas", "year", "emissions_mt_co2eq", "is_estimate", "edgar_edition",
]


def read_edgar_sheet(path: Path, sheet: str) -> pd.DataFrame:
    """Read the sheet exactly as it is in the Excel file."""
    return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")


def tidy_edgar(raw: pd.DataFrame, edition: int) -> pd.DataFrame:
    """Clean and reshape the raw EDGAR sheet (wide) into a long table."""
    settings = get_settings()["edgar"]

    # 1. Drop the empty separator rows the sheet has near the bottom
    df = raw.dropna(subset=["Substance", "Sector", "EDGAR Country Code"]).copy()
    log.info("Dropped %d empty rows", len(raw) - len(df))

    # 2. Wide -> long. Year columns are the ones whose name is a number.
    year_columns = [c for c in df.columns if str(c).strip().split(".")[0].isdigit()]
    long = df.melt(id_vars=ID_COLUMNS, value_vars=year_columns,
                   var_name="year", value_name="emissions_mt_co2eq")
    long = long.rename(columns={
        "Substance": "substance",
        "Sector": "sector",
        "EDGAR Country Code": "country_code",
        "Country": "country_name",
    })

    # 3. Fix types and trim stray spaces
    long["year"] = pd.to_numeric(long["year"]).astype(int)
    long["emissions_mt_co2eq"] = pd.to_numeric(long["emissions_mt_co2eq"], errors="coerce")
    for column in ["substance", "sector", "country_code", "country_name"]:
        long[column] = long[column].astype(str).str.strip()

    # 4. Missing values: EDGAR leaves a cell empty when it has no estimate.
    #    We never turn them into 0 (that would understate totals); we drop them.
    missing = int(long["emissions_mt_co2eq"].isna().sum())
    long = long.dropna(subset=["emissions_mt_co2eq"])
    log.info("Dropped %d empty emission cells (no estimate in EDGAR)", missing)

    # 5. Derived fields
    long["gas"] = long["substance"].map(settings["substances"])  # e.g. GWP_100_AR5_CH4 -> CH4
    long["country_type"] = "country"
    long.loc[long["country_code"].isin(settings["aggregate_codes"]), "country_type"] = "aggregate"
    long.loc[long["country_code"].isin(settings["international_codes"]), "country_type"] = "international"
    long["sector_key"] = long["sector"].str.lower().str.replace(" ", "_")  # folder-friendly name
    long["is_estimate"] = long["year"] >= settings["fast_track_from_year"]
    long["edgar_edition"] = int(edition)

    return long[STAGING_COLUMNS].sort_values(["sector", "country_code", "gas", "year"]).reset_index(drop=True)


def stage_edgar(raw_path: str | None = None, edition: int | None = None) -> str:
    """Read the raw EDGAR file, tidy it and write Parquet partitioned by sector."""
    settings = get_settings()["edgar"]
    edition = int(edition or settings["edition"])
    raw_path = Path(raw_path) if raw_path else edgar_raw_path(edition)

    raw = read_edgar_sheet(raw_path, settings["sheet"])
    log.info("Read %d rows x %d columns from %s", raw.shape[0], raw.shape[1], raw_path.name)
    tidy = tidy_edgar(raw, edition)

    out_dir = reset_dir(STAGING_DIR / "edgar")  # replace the old staging data (safe reruns)
    tidy.to_parquet(out_dir, partition_cols=["sector_key"], index=False, engine="pyarrow")
    log.info("Wrote %d rows to %s (one folder per sector)", len(tidy), out_dir)
    return str(out_dir)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(stage_edgar())
