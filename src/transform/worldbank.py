"""Transform (raw -> staging): flatten the World Bank JSON pages into one table.

Output: data/staging/worldbank/population.parquet
Columns: iso3, wb_name, year, population, is_country, indicator
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pycountry

from src.config import RAW_DIR, STAGING_DIR, get_settings
from src.utils.errors import ExtractionError
from src.utils.files import reset_dir
from src.utils.logger import get_logger

log = get_logger("transform.worldbank")


def latest_pull_dir(indicator: str) -> Path:
    """The most recent complete pull (a folder that has _manifest.json)."""
    pulls = sorted(p for p in (RAW_DIR / "worldbank" / indicator).glob("pulled=*")
                   if (p / "_manifest.json").exists())
    if not pulls:
        raise ExtractionError(f"No complete World Bank pull found for {indicator}. Run the extract step first.")
    return pulls[-1]


def read_pages(folder: Path) -> list[dict]:
    """Read every page file and return all records in one list."""
    records = []
    for page_file in sorted(Path(folder).glob("page_*.json")):
        with open(page_file, encoding="utf-8") as f:
            _page_info, page_records = json.load(f)
        records.extend(page_records or [])
    return records


def is_country_code(code: str, extra_codes: dict) -> bool:
    """True for real countries/territories. Regions like 'WLD' or 'EAS' are not ISO codes."""
    return pycountry.countries.get(alpha_3=code) is not None or code in extra_codes


def tidy_worldbank(records: list[dict]) -> pd.DataFrame:
    """Turn API records into a clean table with one row per country and year."""
    extra_codes = get_settings()["worldbank"]["extra_country_codes"]
    df = pd.DataFrame({
        "iso3": [r.get("countryiso3code") or r["country"]["id"] for r in records],
        "wb_name": [r["country"]["value"] for r in records],
        "year": [r["date"] for r in records],
        "value": [r["value"] for r in records],
        "indicator": [r["indicator"]["id"] for r in records],
    })
    df["year"] = pd.to_numeric(df["year"]).astype(int)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    empty = int(df["value"].isna().sum())
    df = df.dropna(subset=["value"]).copy()
    log.info("Dropped %d records without a value", empty)

    df["population"] = df["value"].round().astype("int64")
    df["is_country"] = df["iso3"].map(lambda code: is_country_code(code, extra_codes))
    return df[["iso3", "wb_name", "year", "population", "is_country", "indicator"]] \
        .sort_values(["iso3", "year"]).reset_index(drop=True)


def stage_worldbank(raw_dir: str | None = None, indicator: str | None = None) -> str:
    """Read the latest raw pull, flatten it and save it as Parquet."""
    indicator = indicator or get_settings()["worldbank"]["indicator"]
    folder = Path(raw_dir) if raw_dir else latest_pull_dir(indicator)
    records = read_pages(folder)
    log.info("Read %d records from %s", len(records), folder)

    df = tidy_worldbank(records)
    out_dir = reset_dir(STAGING_DIR / "worldbank")
    out_file = out_dir / "population.parquet"
    df.to_parquet(out_file, index=False)
    log.info("Wrote %d rows (%d countries, %d regions/groups) to %s", len(df),
             df.loc[df["is_country"], "iso3"].nunique(), df.loc[~df["is_country"], "iso3"].nunique(), out_file)
    return str(out_file)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(stage_worldbank())
