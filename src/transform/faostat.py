"""Transform (raw -> staging): read the FAOSTAT CSV (inside the zip) into one typed, long table.

FAOSTAT publishes the same data in two layouts, and both are accepted:
  normalized: one row per area, item, element, source and year (columns Year, Value, Flag)
  wide:       one row per area, item, element and source, with columns Y1961, Y1961F, ... Y2050, Y2050F

Nothing is filtered here (all areas, activities, gases and sources stay); the curated layer picks what
it needs. Staging only fixes types, adds ISO country codes and flags aggregates and projections.

Output: data/staging/faostat/emissions_totals.parquet
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd
import pycountry

from src.config import RAW_DIR, STAGING_DIR, get_settings
from src.extract.faostat import data_csv_name
from src.utils.errors import DataQualityError, ExtractionError
from src.utils.files import reset_dir
from src.utils.logger import get_logger

log = get_logger("transform.faostat")

ID_COLUMNS = ["Area Code", "Area Code (M49)", "Area", "Item Code", "Item", "Element", "Source", "Unit"]
# Texts that repeat millions of times are read as 'category': each text is stored once (4x less memory)
READ_TYPES = {"Area Code (M49)": "str", "Area": "category", "Item": "category", "Element": "category",
              "Source": "category", "Unit": "category", "Flag": "category"}
STAGING_COLUMNS = ["area_code", "m49_code", "iso3", "area", "is_aggregate", "item_code", "item", "element",
                   "source", "unit", "year", "value", "flag", "is_projection"]


def latest_faostat_file() -> Path:
    """The most recent complete download (its .meta.json is written last)."""
    files = sorted(p for p in (RAW_DIR / "faostat").glob("pulled=*/*.zip")
                   if p.with_name(p.name + ".meta.json").exists())
    if not files:
        raise ExtractionError("No complete FAOSTAT download found. Run the extract step first.")
    return files[-1]


def read_faostat_csv(zip_path: Path) -> pd.DataFrame:
    """Read the data CSV straight from the zip (no need to unzip it on disk)."""
    member = data_csv_name(zip_path)
    for encoding in ("utf-8", "latin-1"):  # current files are UTF-8; older ones were Latin-1
        try:
            with zipfile.ZipFile(zip_path) as archive, archive.open(member) as f:
                header = pd.read_csv(f, nrows=0, encoding=encoding).columns
            wanted = {c: t for c, t in READ_TYPES.items() if c in header}
            wanted.update({c: "category" for c in header if re.fullmatch(r"Y\d{4}F", c)})  # wide flags
            with zipfile.ZipFile(zip_path) as archive, archive.open(member) as f:
                raw = pd.read_csv(f, encoding=encoding, dtype=wanted,
                                  usecols=lambda c: c in ID_COLUMNS or c in ("Year", "Value", "Flag")
                                  or bool(re.fullmatch(r"Y\d{4}F?", c)))
            log.info("Read %s (%s): %d rows x %d columns", member, encoding, raw.shape[0], raw.shape[1])
            return raw
        except UnicodeDecodeError:
            log.warning("%s is not %s text, trying the next encoding", member, encoding)
    raise ExtractionError(f"Could not read {member}")  # not reached: Latin-1 can decode any bytes


def wide_to_long(raw: pd.DataFrame) -> pd.DataFrame:
    """Wide layout -> the normalized layout (columns Year, Value, Flag)."""
    year_columns = [c for c in raw.columns if re.fullmatch(r"Y\d{4}", c)]
    ids = [c for c in ID_COLUMNS if c in raw.columns]
    long = raw.melt(id_vars=ids, value_vars=year_columns, var_name="Year", value_name="Value")
    # melt stacks the columns in the same order, so the flags line up with the values row by row
    long["Flag"] = raw.melt(value_vars=[c + "F" for c in year_columns], value_name="Flag")["Flag"].to_numpy()
    long["Year"] = long["Year"].str[1:].astype(int)  # 'Y2023' -> 2023
    return long


def iso3_from_m49(m49: str) -> str | None:
    """UN M49 area code -> ISO 3166 alpha-3 code ('608' -> 'PHL'). None for regions and former states."""
    country = pycountry.countries.get(numeric=str(m49).zfill(3))
    return country.alpha_3 if country else None


def tidy_faostat(raw: pd.DataFrame) -> pd.DataFrame:
    """Both layouts -> one long table with clean names, types and flags."""
    settings = get_settings()["faostat"]
    layout = "normalized" if {"Year", "Value"} <= set(raw.columns) else "wide"
    missing = [c for c in ID_COLUMNS if c not in raw.columns]
    if missing or (layout == "wide" and not any(re.fullmatch(r"Y\d{4}", c) for c in raw.columns)):
        raise DataQualityError(f"The FAOSTAT file does not have the expected columns (missing: {missing})")
    df = raw if layout == "normalized" else wide_to_long(raw)
    log.info("Layout: %s", layout)

    # Empty values mean "no estimate"; they are dropped, never turned into 0
    empty = int(df["Value"].isna().sum())
    df = df.dropna(subset=["Value"])
    log.info("Dropped %d empty values", empty)

    df = df.rename(columns={"Area Code": "area_code", "Area Code (M49)": "m49_code", "Area": "area",
                            "Item Code": "item_code", "Item": "item", "Element": "element", "Source": "source",
                            "Unit": "unit", "Year": "year", "Value": "value", "Flag": "flag"})
    df["area_code"] = df["area_code"].astype(int)
    df["item_code"] = df["item_code"].astype(int)
    df["year"] = df["year"].astype(int)
    df["value"] = df["value"].astype(float)

    # M49 codes come with a leading apostrophe ("'608") so Excel keeps the zeros
    df["m49_code"] = df["m49_code"].astype(str).str.lstrip("'")
    iso3_by_m49 = {code: iso3_from_m49(code) for code in df["m49_code"].unique()}
    df["iso3"] = df["m49_code"].map(iso3_by_m49)

    # Regions (codes >= 5000) and 'China' (mainland + Hong Kong + Macao + Taiwan) are sums of other rows
    df["is_aggregate"] = (df["area_code"] >= settings["world_area_code"]) | (df["area_code"] == settings["china_area_code"])
    df.loc[df["is_aggregate"], "iso3"] = None
    df["is_projection"] = df["flag"] == settings["projection_flag"]  # 2030 and 2050 are projections
    return df[STAGING_COLUMNS].sort_values(["area_code", "item_code", "element", "source", "year"]) \
        .reset_index(drop=True)


def stage_faostat(raw_path: str | None = None) -> str:
    """Read the latest raw FAOSTAT file, tidy it and write one Parquet file."""
    raw_path = Path(raw_path) if raw_path else latest_faostat_file()
    tidy = tidy_faostat(read_faostat_csv(raw_path))

    out_dir = reset_dir(STAGING_DIR / "faostat")  # replace the old staging data (safe reruns)
    out_file = out_dir / "emissions_totals.parquet"
    tidy.to_parquet(out_file, index=False)
    countries = tidy.loc[~tidy["is_aggregate"], "area_code"].nunique()
    log.info("Wrote %d rows (%d areas: %d countries, %d aggregates; years %d-%d) to %s", len(tidy),
             tidy["area_code"].nunique(), countries, tidy["area_code"].nunique() - countries,
             tidy["year"].min(), tidy["year"].max(), out_file)
    return str(out_file)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(stage_faostat())
