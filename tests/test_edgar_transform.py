"""Tests for reshaping the EDGAR sheet (raw -> staging)."""
import pandas as pd

from src.transform.edgar import tidy_edgar

RAW = pd.DataFrame({
    "Substance": ["GWP_100_AR5_CH4", "CO2", "GWP_100_AR5_CH4", None],
    "Sector": ["Agriculture", "Agriculture", "Agriculture", None],
    "EDGAR Country Code": ["PHL", "PHL", "GLOBAL TOTAL", None],
    "Country": ["Philippines", "Philippines", "GLOBAL TOTAL", None],
    2022: [40.0, 1.5, 4000.0, None],
    2023: [41.0, None, 4100.0, None],   # missing CO2 value in 2023
})


def test_wide_becomes_long_and_blank_rows_are_dropped():
    tidy = tidy_edgar(RAW, edition=2026)
    # 3 real rows x 2 years = 6 cells, minus 1 empty cell = 5 rows
    assert len(tidy) == 5
    assert set(tidy["year"]) == {2022, 2023}


def test_missing_values_are_dropped_not_zero():
    tidy = tidy_edgar(RAW, edition=2026)
    co2 = tidy[(tidy["country_code"] == "PHL") & (tidy["gas"] == "CO2")]
    assert list(co2["year"]) == [2022]           # 2023 was empty -> no row
    assert (tidy["emissions_mt_co2eq"] > 0).all()  # nothing turned into 0


def test_gas_codes_country_types_and_estimates():
    tidy = tidy_edgar(RAW, edition=2026)
    assert set(tidy["gas"]) == {"CH4", "CO2"}
    assert tidy.loc[tidy["country_code"] == "GLOBAL TOTAL", "country_type"].eq("aggregate").all()
    assert tidy.loc[tidy["country_code"] == "PHL", "country_type"].eq("country").all()
    assert tidy.loc[tidy["year"] == 2023, "is_estimate"].all()      # fast-track from 2023
    assert not tidy.loc[tidy["year"] == 2022, "is_estimate"].any()
    assert (tidy["sector_key"] == "agriculture").all()
