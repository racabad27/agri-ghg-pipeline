from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import CONFIG_DIR, CURATED_DIR, STAGING_DIR, get_settings
from src.utils.files import reset_dir
from src.utils.logger import get_logger

log = get_logger("transform.curated")


def read_agriculture_partition() -> pd.DataFrame:
    """Read only the 'agriculture' folder of the sector-partitioned staging data.
    The other seven sector folders are never opened (partition pruning)."""
    sector_key = get_settings()["curated"]["focus_sector"].lower().replace(" ", "_")
    df = pd.read_parquet(STAGING_DIR / "edgar", filters=[("sector_key", "==", sector_key)])
    log.info("Read %d rows from the '%s' partition", len(df), sector_key)
    return df


def build_dim_country(emissions: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """One row per EDGAR country code, plus the World Bank codes whose population it needs."""
    countries = emissions[["country_code", "country_name"]].drop_duplicates("country_code").copy()
    wb_codes = mapping.groupby("edgar_code")["wb_code"].apply(lambda codes: ";".join(sorted(codes)))
    countries["wb_codes"] = countries["country_code"].map(wb_codes).fillna(countries["country_code"])
    countries["is_merged"] = countries["wb_codes"].str.contains(";")
    return countries.sort_values("country_code").reset_index(drop=True)


def population_for_edgar_countries(population: pd.DataFrame, dim_country: pd.DataFrame) -> pd.DataFrame:
    """Add up World Bank populations for EDGAR's merged countries (e.g. SDN = Sudan + South Sudan).

    Rule: a merged country only gets a population for a year when EVERY part has data.
    Example: the World Bank has Palestine only from 1990, so Israel+Palestine starts in 1990.
    """
    parts = (dim_country[["country_code", "wb_codes"]]
             .assign(wb_code=lambda d: d["wb_codes"].str.split(";"))
             .explode("wb_code"))
    expected_parts = parts.groupby("country_code")["wb_code"].nunique()

    countries_only = population[population["is_country"]]
    joined = parts.merge(countries_only, left_on="wb_code", right_on="iso3", how="inner")
    result = (joined.groupby(["country_code", "year"])
              .agg(population=("population", "sum"), parts_found=("wb_code", "nunique"))
              .reset_index())
    complete = result["parts_found"] == result["country_code"].map(expected_parts)
    log.info("Population matched for %d country-years (%d dropped: missing parts)",
             int(complete.sum()), int((~complete).sum()))
    return result.loc[complete, ["country_code", "year", "population"]].reset_index(drop=True)


def build_country_year(by_gas: pd.DataFrame, population: pd.DataFrame, edition: int) -> pd.DataFrame:
    """Main data product: one row per country and year with totals, per-person and shares."""
    wide = (by_gas.pivot_table(index=["country_code", "year"], columns="gas",
                               values="emissions_mt_co2eq", aggfunc="sum")
            .reset_index().rename_axis(columns=None))
    for gas in ["CO2", "CH4", "N2O"]:
        if gas not in wide.columns:
            wide[gas] = np.nan
    wide = wide.rename(columns={"CO2": "co2_mt", "CH4": "ch4_mt", "N2O": "n2o_mt"})
    wide["total_mt"] = wide[["co2_mt", "ch4_mt", "n2o_mt"]].sum(axis=1, min_count=1)

    # Share of the world total in the same year (world = sum of all countries)
    wide["share_of_world_pct"] = 100 * wide["total_mt"] / wide.groupby("year")["total_mt"].transform("sum")

    # Change from the previous year, per country
    wide = wide.sort_values(["country_code", "year"])
    wide["yoy_change_pct"] = (wide.groupby("country_code")["total_mt"].pct_change() * 100) \
        .replace([np.inf, -np.inf], np.nan)

    # Per person: Mt -> tonnes (x 1,000,000) divided by population
    wide = wide.merge(population, on=["country_code", "year"], how="left")
    wide["t_per_person"] = wide["total_mt"] * 1_000_000 / wide["population"]

    estimate = by_gas.groupby(["country_code", "year"])["is_estimate"].any().reset_index()
    wide = wide.merge(estimate, on=["country_code", "year"], how="left")
    wide["population"] = wide["population"].astype("Int64")
    wide["edgar_edition"] = int(edition)
    columns = ["country_code", "year", "co2_mt", "ch4_mt", "n2o_mt", "total_mt", "share_of_world_pct",
               "yoy_change_pct", "population", "t_per_person", "is_estimate", "edgar_edition"]
    return wide[columns].reset_index(drop=True)


def build_curated() -> dict:
    """Build all curated tables and return their file paths."""
    focus_gases = get_settings()["curated"]["focus_gases"]
    staged = read_agriculture_partition()

    # Keep real countries only (drop GLOBAL TOTAL / EU27 so nothing is counted twice)
    emissions = staged[(staged["country_type"] == "country") & staged["gas"].isin(focus_gases)].copy()
    edition = int(emissions["edgar_edition"].max())

    mapping = pd.read_csv(CONFIG_DIR / "country_mapping.csv")
    dim_country = build_dim_country(emissions, mapping)

    by_gas = emissions[["country_code", "gas", "year", "emissions_mt_co2eq", "is_estimate", "edgar_edition"]] \
        .sort_values(["country_code", "gas", "year"]).reset_index(drop=True)

    population_raw = pd.read_parquet(STAGING_DIR / "worldbank" / "population.parquet")
    population = population_for_edgar_countries(population_raw, dim_country)
    country_year = build_country_year(by_gas, population, edition)

    out_dir = reset_dir(CURATED_DIR)
    paths = {}
    for name, table in {"dim_country": dim_country, "agri_emissions_by_gas": by_gas,
                        "population": population, "agri_country_year": country_year}.items():
        path = out_dir / f"{name}.parquet"
        table.to_parquet(path, index=False)
        paths[name] = str(path)
        log.info("Wrote %s: %d rows", path.name, len(table))
    return paths


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(build_curated())
