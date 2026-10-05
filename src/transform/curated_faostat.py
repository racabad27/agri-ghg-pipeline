from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import CONFIG_DIR, CURATED_DIR, OUTPUTS_DIR, STAGING_DIR, get_settings
from src.utils.logger import get_logger

log = get_logger("transform.curated_faostat")


def read_faostat_scope() -> pd.DataFrame:
    """Read only what we use from staging: FAO Tier 1, CO2eq (AR5), the 8 activities, from 2000,
    countries only (no regions, no 'China' aggregate), no projections."""
    f = get_settings()["faostat"]
    df = pd.read_parquet(
        STAGING_DIR / "faostat" / "emissions_totals.parquet",
        columns=["area_code", "iso3", "area", "is_aggregate", "item_code", "element", "source", "year",
                 "value", "is_projection"],
        filters=[("source", "==", f["source"]), ("element", "==", f["element"]),
                 ("item_code", "in", list(f["activities"])), ("year", ">=", f["first_year"])],
    )
    df = df[~df["is_aggregate"] & ~df["is_projection"]]
    df["area"] = df["area"].astype(str)
    log.info("Read %d FAOSTAT rows in scope (%d areas, years %d-%d)", len(df), df["area_code"].nunique(),
             df["year"].min(), df["year"].max())
    return df.reset_index(drop=True)


def edgar_codes_for(df: pd.DataFrame, area_mapping: pd.DataFrame, country_mapping: pd.DataFrame) -> pd.Series:
    """EDGAR country code for every FAOSTAT row.

    1. special FAOSTAT areas without an ISO code (config/faostat_area_mapping.csv), e.g. Sudan (former) -> SDN
    2. otherwise the ISO3 code, translated for EDGAR's merged countries (config/country_mapping.csv),
       e.g. SSD (South Sudan) -> SDN, MCO (Monaco) -> FRA
    """
    special = dict(zip(area_mapping["fao_area_code"], area_mapping["edgar_code"]))
    merged = dict(zip(country_mapping["wb_code"], country_mapping["edgar_code"]))  # wb_code = ISO3 code
    from_iso3 = df["iso3"].map(lambda code: merged.get(code, code) if isinstance(code, str) else None)
    return df["area_code"].map(special).fillna(from_iso3)


def build_dim_activity() -> pd.DataFrame:
    activities = get_settings()["faostat"]["activities"]
    return pd.DataFrame({
        "activity_code": list(activities),
        "activity_name": [a["name"] for a in activities.values()],
        "activity_group": [a["group"] for a in activities.values()],
    }).astype({"activity_code": "int64"})


def build_by_activity(scope: pd.DataFrame, dim_country: pd.DataFrame, dim_activity: pd.DataFrame,
                      area_mapping: pd.DataFrame, country_mapping: pd.DataFrame) -> tuple:
    """Country x activity x year in Mt CO2eq. Returns (table, unmatched areas, rejected rows)."""
    df = scope.assign(country_code=edgar_codes_for(scope, area_mapping, country_mapping))

    # 1. Areas EDGAR does not list separately: keep a record, then leave them out
    known = df["country_code"].isin(dim_country["country_code"])
    unmatched = (df[~known].groupby(["area_code", "area"], as_index=False)
                 .agg(iso3=("iso3", "first"), rows=("value", "size"), kt_all_years=("value", "sum")))
    if len(unmatched):
        log.warning("%d FAOSTAT areas have no EDGAR code and are left out: %s", len(unmatched),
                    ", ".join(unmatched["area"]))

    # 2. Negative emissions are impossible for these activities: reject them, with the reason
    negative = known & (df["value"] < 0)
    rejected = df.loc[negative, ["area_code", "area", "country_code", "item_code", "year", "value"]] \
        .assign(reason="negative emissions are impossible for this activity")
    if len(rejected):
        log.warning("Rejected %d rows with negative emissions (see faostat_rejected_rows.csv)", len(rejected))

    # 3. Add up parts that EDGAR reports as one country (e.g. Sudan + South Sudan), kt -> Mt
    good = df[known & ~negative]
    table = (good.groupby(["country_code", "item_code", "year"], as_index=False)["value"].sum()
             .rename(columns={"item_code": "activity_code"}))
    table["emissions_mt_co2eq"] = table["value"] / 1000
    table = table.merge(dim_activity, on="activity_code", how="left")
    table = table[["country_code", "activity_code", "activity_name", "activity_group", "year",
                   "emissions_mt_co2eq"]].rename(columns={"activity_name": "activity"})
    return table.sort_values(["country_code", "activity_code", "year"]).reset_index(drop=True), unmatched, rejected


def build_comparison(by_activity: pd.DataFrame, country_year: pd.DataFrame) -> pd.DataFrame:
    """EDGAR and FAOSTAT agriculture totals side by side (only countries and years that both have)."""
    faostat = (by_activity.groupby(["country_code", "year"], as_index=False)["emissions_mt_co2eq"].sum()
               .rename(columns={"emissions_mt_co2eq": "faostat_total_mt"}))
    edgar = country_year[["country_code", "year", "total_mt"]].rename(columns={"total_mt": "edgar_total_mt"})
    both = edgar.merge(faostat, on=["country_code", "year"], how="inner")
    both["difference_mt"] = both["faostat_total_mt"] - both["edgar_total_mt"]
    both["difference_pct"] = (100 * both["difference_mt"] / both["edgar_total_mt"]).replace([np.inf, -np.inf], np.nan)
    return both.sort_values(["country_code", "year"]).reset_index(drop=True)


def build_faostat_curated() -> dict:
    """Build the FAOSTAT curated tables and return their file paths."""
    dim_country = pd.read_parquet(CURATED_DIR / "dim_country.parquet")
    country_year = pd.read_parquet(CURATED_DIR / "agri_country_year.parquet")
    area_mapping = pd.read_csv(CONFIG_DIR / "faostat_area_mapping.csv")
    country_mapping = pd.read_csv(CONFIG_DIR / "country_mapping.csv")

    dim_activity = build_dim_activity()
    by_activity, unmatched, rejected = build_by_activity(read_faostat_scope(), dim_country, dim_activity,
                                                         area_mapping, country_mapping)
    comparison = build_comparison(by_activity, country_year)

    reports = OUTPUTS_DIR / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    unmatched.to_csv(reports / "faostat_unmatched_areas.csv", index=False)
    rejected.to_csv(reports / "faostat_rejected_rows.csv", index=False)

    paths = {}
    for name, table in {"dim_activity": dim_activity, "agri_emissions_by_activity": by_activity,
                        "edgar_vs_faostat": comparison}.items():
        path = CURATED_DIR / f"{name}.parquet"
        table.to_parquet(path, index=False)
        paths[name] = str(path)
        log.info("Wrote %s: %d rows", path.name, len(table))
    return paths


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(build_faostat_curated())
