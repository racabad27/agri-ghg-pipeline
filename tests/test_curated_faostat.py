"""Tests for FAOSTAT in the curated layer: matching to EDGAR countries, rejected rows, the comparison."""
import pandas as pd
import pytest

from src.transform.curated_faostat import build_by_activity, build_comparison, build_dim_activity

DIM_COUNTRY = pd.DataFrame({"country_code": ["SDN", "PHL"]})
AREA_MAPPING = pd.DataFrame({"fao_area_code": [206], "edgar_code": ["SDN"]})
COUNTRY_MAPPING = pd.DataFrame({"wb_code": ["SDN", "SSD"], "edgar_code": ["SDN", "SDN"]})
SCOPE = pd.DataFrame({
    "area_code": [206, 276, 277, 171, 171, 227],
    "area": ["Sudan (former)", "Sudan", "South Sudan", "Philippines", "Philippines", "Tuvalu"],
    "iso3": [None, "SDN", "SSD", "PHL", "PHL", "TUV"],
    "item_code": [5058, 5058, 5058, 5060, 5061, 5058],
    "year": [2011, 2012, 2012, 2023, 2023, 2023],
    "value": [20000.0, 15000.0, 9000.0, 45100.0, -0.5, 1.0],   # kt
})


def build():
    return build_by_activity(SCOPE, DIM_COUNTRY, build_dim_activity(), AREA_MAPPING, COUNTRY_MAPPING)


def test_areas_are_matched_to_edgar_countries():
    table, unmatched, _ = build()
    sdn = table[table["country_code"] == "SDN"].set_index("year")["emissions_mt_co2eq"]
    assert sdn[2011] == pytest.approx(20.0)             # Sudan (former), via faostat_area_mapping.csv
    assert sdn[2012] == pytest.approx(24.0)             # Sudan + South Sudan added up, kt -> Mt
    assert list(unmatched["area"]) == ["Tuvalu"]        # no EDGAR code: reported, not loaded
    assert "TUV" not in set(table["country_code"])


def test_negative_emissions_are_rejected_not_loaded():
    table, _, rejected = build()
    assert len(rejected) == 1 and rejected["value"].iloc[0] == -0.5
    phl = table[table["country_code"] == "PHL"]
    assert list(phl["activity"]) == ["Rice cultivation"]  # the negative fertilizer row is gone
    assert (table["emissions_mt_co2eq"] >= 0).all()


def test_edgar_vs_faostat_difference():
    table, _, _ = build()
    country_year = pd.DataFrame({"country_code": ["PHL", "PHL"], "year": [2023, 2024], "total_mt": [50.0, 51.0]})
    cmp = build_comparison(table, country_year)
    assert len(cmp) == 1                                 # only years both sources have
    row = cmp.iloc[0]
    assert row["faostat_total_mt"] == pytest.approx(45.1)
    assert row["difference_pct"] == pytest.approx(-9.8)  # (45.1 - 50) / 50
