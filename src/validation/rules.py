"""Data-quality rules for each dataset. Each function reads one layer, runs the checks
from checks.py and returns the report (or raises DataQualityError)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.config import CURATED_DIR, STAGING_DIR, get_settings
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


# ------------------------------------------------------------------ curated layer
def validate_curated() -> dict:
    v = get_settings()["validation"]
    country_year = pd.read_parquet(CURATED_DIR / "agri_country_year.parquet")
    by_gas = pd.read_parquet(CURATED_DIR / "agri_emissions_by_gas.parquet")
    dim_country = pd.read_parquet(CURATED_DIR / "dim_country.parquet")

    # Population coverage: share of emissions (years that have population data) with a population value
    with_pop_years = country_year.loc[country_year["population"].notna(), "year"].unique()
    in_scope = country_year[country_year["year"].isin(with_pop_years)]
    coverage = 100 * in_scope.loc[in_scope["population"].notna(), "total_mt"].sum() / in_scope["total_mt"].sum()

    # Shares of world emissions must add up to 100% every year
    share_sums = country_year.groupby("year")["share_of_world_pct"].sum()
    share_gap = float((share_sums - 100).abs().max())

    unknown_countries = sorted(set(by_gas["country_code"]) - set(dim_country["country_code"]))
    results = [
        expect_unique(country_year, ["country_code", "year"]),
        expect_unique(by_gas, ["country_code", "gas", "year"]),
        expect_not_null(country_year, ["country_code", "year", "total_mt", "share_of_world_pct"]),
        expect_values_in(by_gas, "gas", get_settings()["curated"]["focus_gases"]),
        expect_true("referential integrity: every country is in dim_country", not unknown_countries,
                    f"unknown codes: {unknown_countries[:10]}"),
        expect_between(country_year, "total_mt", min_value=0),
        expect_between(country_year, "t_per_person", min_value=0, max_value=v["max_t_per_person"]),
        expect_true(f"population coverage >= {v['min_population_coverage_pct']}% of emissions",
                    coverage >= v["min_population_coverage_pct"], f"coverage {coverage:.2f}%"),
        expect_true("shares of world emissions add up to 100% each year", share_gap < 1e-6,
                    f"largest gap {share_gap:.2e} percentage points"),
    ]
    return run_checks("curated", results)


def validate_faostat_curated() -> dict:
    from src.transform.curated_faostat import read_faostat_scope

    f, v = get_settings()["faostat"], get_settings()["validation"]
    by_activity = pd.read_parquet(CURATED_DIR / "agri_emissions_by_activity.parquet")
    comparison = pd.read_parquet(CURATED_DIR / "edgar_vs_faostat.parquet")
    dim_country = pd.read_parquet(CURATED_DIR / "dim_country.parquet")

    # Coverage: share of FAOSTAT's country emissions (latest year) that reached the curated table
    scope = read_faostat_scope()
    latest = int(scope["year"].max())
    kept_kt = 1000 * by_activity.loc[by_activity["year"] == latest, "emissions_mt_co2eq"].sum()
    coverage = 100 * kept_kt / scope.loc[scope["year"] == latest, "value"].sum()

    # The two sources must roughly agree on the world total (a unit or mapping error would not)
    world = comparison.groupby("year")[["edgar_total_mt", "faostat_total_mt"]].sum()
    world_gap = float((100 * (world["faostat_total_mt"] - world["edgar_total_mt"]).abs()
                       / world["edgar_total_mt"]).max())

    unknown_countries = sorted(set(by_activity["country_code"]) - set(dim_country["country_code"]))
    results = [
        expect_unique(by_activity, ["country_code", "activity_code", "year"]),
        expect_not_null(by_activity, ["country_code", "activity_code", "activity", "activity_group", "year",
                                      "emissions_mt_co2eq"]),
        expect_values_in(by_activity, "activity_code", list(f["activities"])),
        expect_between(by_activity, "emissions_mt_co2eq", min_value=0),
        expect_true("referential integrity: every country is in dim_country", not unknown_countries,
                    f"unknown codes: {unknown_countries[:10]}"),
        expect_unique(comparison, ["country_code", "year"]),
        expect_true(f"FAOSTAT coverage >= {v['min_faostat_coverage_pct']}% of emissions ({latest})",
                    coverage >= v["min_faostat_coverage_pct"], f"coverage {coverage:.3f}%"),
        expect_true(f"EDGAR and FAOSTAT world totals agree within {v['max_edgar_faostat_gap_pct']}%",
                    world_gap <= v["max_edgar_faostat_gap_pct"],
                    f"largest gap {world_gap:.1f}% over {len(world)} years"),
    ]
    return run_checks("curated_faostat", results)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    validate_edgar_staging()
    validate_worldbank_staging()
    validate_faostat_staging()
    validate_curated()
    validate_faostat_curated()
