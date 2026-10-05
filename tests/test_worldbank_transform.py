"""Tests for flattening World Bank API records (raw -> staging)."""
from src.transform.worldbank import tidy_worldbank


def record(code, name, year, value):
    return {"indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
            "country": {"id": code[:2], "value": name}, "countryiso3code": code,
            "date": str(year), "value": value, "unit": "", "obs_status": "", "decimal": 0}


RECORDS = [
    record("PHL", "Philippines", 2024, 115843670),
    record("PHL", "Philippines", 2025, None),        # not published yet
    record("WLD", "World", 2024, 8141808945),         # a region, not a country
    record("XKX", "Kosovo", 2024, 1500000),           # real place, not an ISO code
]


def test_types_and_empty_values():
    df = tidy_worldbank(RECORDS)
    assert len(df) == 3                                # the empty 2025 value is dropped
    assert str(df["year"].dtype) == "int64"
    assert str(df["population"].dtype) == "int64"


def test_regions_are_not_countries():
    df = tidy_worldbank(RECORDS).set_index("iso3")
    assert df.loc["PHL", "is_country"]
    assert df.loc["XKX", "is_country"]                 # listed in extra_country_codes
    assert not df.loc["WLD", "is_country"]
