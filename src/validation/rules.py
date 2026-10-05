"""Data-quality rules for each dataset. Each function reads one layer, runs the checks
from checks.py and returns the report (or raises DataQualityError)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.config import STAGING_DIR, get_settings
from src.validation.checks import (
    CheckResult, expect_between, expect_columns, expect_not_null, expect_row_count_at_least,
    expect_true, expect_unique, expect_values_in, run_checks,
)


# ---------------------------------------------------------------- staging: EDGAR
def world_total_matches_countries(df: pd.DataFrame) -> CheckResult:
    """Business rule: for every sector, gas and year, EDGAR's GLOBAL TOTAL row must equal
    the sum of all countries plus international aviation and shipping."""
    parts = (df[df["country_type"] != "aggregate"]
             .groupby(["sector", "gas", "year"])["emissions_mt_co2eq"].sum())
    world = (df[df["country_code"] == "GLOBAL TOTAL"]
             .set_index(["sector", "gas", "year"])["emissions_mt_co2eq"])
    both = pd.concat({"parts": parts, "world": world}, axis=1).dropna()
    gap = ((both["parts"] - both["world"]).abs() / both["world"].where(both["world"] > 0)).max()
    return expect_true("business rule: GLOBAL TOTAL = sum of countries", gap < 1e-6,
                       f"largest relative gap {gap:.2e} over {len(both):,} sector-gas-years")


def validate_edgar_staging() -> dict:
    s, v = get_settings()["edgar"], get_settings()["validation"]
    df = pd.read_parquet(STAGING_DIR / "edgar")
    last_year = int(df["edgar_edition"].max()) - 1  # the 2026 edition covers up to 2025
    results = [
        expect_columns(df, ["country_code", "country_name", "country_type", "sector", "gas",
                            "year", "emissions_mt_co2eq", "is_estimate", "edgar_edition"]),
        expect_not_null(df, ["country_code", "sector", "gas", "year", "emissions_mt_co2eq"]),
        expect_unique(df, ["country_code", "sector", "gas", "year"]),
        expect_values_in(df, "sector", s["sectors"]),
        expect_values_in(df, "gas", list(s["substances"].values())),
        expect_between(df, "emissions_mt_co2eq", min_value=0),
        expect_between(df, "year", min_value=s["first_year"], max_value=last_year),
        expect_row_count_at_least(df, v["min_edgar_rows"]),
        world_total_matches_countries(df),
    ]
    return run_checks("edgar_staging", results)


# ----------------------------------------------------------- staging: World Bank
def world_population_matches_countries(df: pd.DataFrame) -> CheckResult:
    """Business rule: the World Bank 'World' (WLD) total should equal the sum of countries.
    A small gap is normal (rounding), so this is a warning, not an error."""
    countries = df[df["is_country"]].groupby("year")["population"].sum()
    world = df[df["iso3"] == "WLD"].set_index("year")["population"]
    both = pd.concat({"countries": countries, "world": world}, axis=1).dropna()
    gap = ((both["countries"] - both["world"]).abs() / both["world"]).max() if len(both) else 1.0
    return expect_true("business rule: World population = sum of countries (within 0.5%)",
                       gap <= 0.005, f"largest relative gap {gap:.4%} over {len(both)} years",
                       severity="warning")


def validate_worldbank_staging() -> dict:
    w, v = get_settings()["worldbank"], get_settings()["validation"]
    df = pd.read_parquet(STAGING_DIR / "worldbank" / "population.parquet")
    results = [
        expect_columns(df, ["iso3", "wb_name", "year", "population", "is_country", "indicator"]),
        expect_not_null(df, ["iso3", "year", "population"]),
        expect_unique(df, ["iso3", "year"]),
        expect_between(df, "population", min_value=1),
        expect_between(df, "year", min_value=w["first_year"], max_value=date.today().year),
        expect_row_count_at_least(df, v["min_worldbank_rows"]),
        world_population_matches_countries(df),
    ]
    return run_checks("worldbank_staging", results)


# -------------------------------------------------------------- staging: FAOSTAT
def faostat_activity_rows(df: pd.DataFrame) -> pd.DataFrame:
    """The rows our project uses: FAO Tier 1, CO2eq (AR5), the 8 activities, from 2000, no projections."""
    f = get_settings()["faostat"]
    return df[(df["source"] == f["source"]) & (df["element"] == f["element"])
              & df["item_code"].isin(list(f["activities"])) & (df["year"] >= f["first_year"])
              & ~df["is_projection"]]


def relative_gap(parts: pd.Series, total: pd.Series) -> tuple[float, int]:
    """Largest relative difference between two series with the same index, and how many were compared."""
    both = pd.concat({"parts": parts, "total": total}, axis=1).dropna()
    if both.empty:
        return 1.0, 0
    return float(((both["parts"] - both["total"]).abs() / both["total"].abs()).max()), len(both)


def faostat_world_matches_countries(activities: pd.DataFrame) -> CheckResult:
    """Business rule: FAOSTAT's 'World' must equal the sum of all countries, every year."""
    f = get_settings()["faostat"]
    countries = activities[~activities["is_aggregate"]].groupby("year")["value"].sum()
    world = activities[activities["area_code"] == f["world_area_code"]].groupby("year")["value"].sum()
    gap, n = relative_gap(countries, world)
    return expect_true("business rule: World = sum of countries (8 activities)", gap < 0.001,
                       f"largest relative gap {gap:.2e} over {n} years")


def faostat_china_matches_parts(activities: pd.DataFrame) -> CheckResult:
    """Business rule: 'China' must equal mainland + Hong Kong + Macao + Taiwan. This proves that
    leaving 'China' out (and keeping the 4 parts) counts nothing twice and loses nothing."""
    f = get_settings()["faostat"]
    china = activities[activities["area_code"] == f["china_area_code"]].groupby("year")["value"].sum()
    parts = activities[activities["area_code"].isin(f["china_parts"])].groupby("year")["value"].sum()
    gap, n = relative_gap(parts, china)
    return expect_true("business rule: 'China' = mainland + Hong Kong + Macao + Taiwan", gap < 0.001,
                       f"largest relative gap {gap:.2e} over {n} years")


def faostat_activities_match_subtotals(df: pd.DataFrame) -> CheckResult:
    """Business rule: for every area and year, the 8 activities add up to FAOSTAT's own subtotals
    'Emissions from crops' + 'Emissions from livestock' (small rounding differences allowed)."""
    f, tolerance = get_settings()["faostat"], get_settings()["validation"]["faostat_tolerance_kt"]
    scope = df[(df["source"] == f["source"]) & (df["element"] == f["element"])
               & (df["year"] >= f["first_year"]) & ~df["is_projection"]]
    activities = scope[scope["item_code"].isin(list(f["activities"]))].groupby(["area_code", "year"])["value"].sum()
    subtotals = scope[scope["item_code"].isin(f["subtotal_items"])].groupby(["area_code", "year"])["value"].sum()
    both = pd.concat({"activities": activities, "subtotals": subtotals}, axis=1).dropna()
    gap = float((both["activities"] - both["subtotals"]).abs().max()) if len(both) else float("inf")
    return expect_true(f"business rule: 8 activities = FAOSTAT crops + livestock subtotals (within {tolerance} kt)",
                       gap <= tolerance, f"largest gap {gap:.3f} kt over {len(both):,} area-years")


def validate_faostat_staging() -> dict:
    f, v = get_settings()["faostat"], get_settings()["validation"]
    df = pd.read_parquet(STAGING_DIR / "faostat" / "emissions_totals.parquet")
    activities = faostat_activity_rows(df)
    future = df[df["year"] > date.today().year]
    results = [
        expect_columns(df, ["area_code", "m49_code", "iso3", "area", "is_aggregate", "item_code", "item",
                            "element", "source", "unit", "year", "value", "flag", "is_projection"]),
        expect_not_null(df, ["area_code", "area", "item_code", "element", "source", "unit", "year", "value"]),
        expect_unique(df, ["area_code", "item_code", "element", "source", "year"]),
        expect_values_in(df, "unit", [f["unit"]]),
        expect_row_count_at_least(df, v["min_faostat_rows"]),
        expect_true("future years are only projections (flag F)", bool(future["is_projection"].all()),
                    f"{int((~future['is_projection']).sum())} future rows without the projection flag"),
        expect_between(activities, "value", min_value=0, severity="warning"),  # removed in the curated layer
        faostat_world_matches_countries(activities),
        faostat_china_matches_parts(activities),
        faostat_activities_match_subtotals(df),
    ]
    return run_checks("faostat_staging", results)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    validate_edgar_staging()
    validate_worldbank_staging()
    validate_faostat_staging()
