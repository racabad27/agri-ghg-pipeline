"""Tests for reading FAOSTAT data (raw -> staging): both layouts, country codes and flags."""
import pandas as pd
import pytest

from src.transform.faostat import tidy_faostat
from src.utils.errors import DataQualityError

ID = {"Item Code": 5060, "Item": "Rice Cultivation", "Element": "Emissions (CO2eq) (AR5)",
      "Source": "FAO TIER 1", "Unit": "kt"}
AREAS = [(171, "'608", "Philippines"), (5000, "'001", "World"), (351, "'159", "China")]
# (area code, year, value, flag); the Philippines has no value for 2022 in this example
VALUES = [(171, 2023, 45.1, "E"), (171, 2030, 47.0, "F"),
          (5000, 2022, 900.0, "E"), (5000, 2023, 910.0, "E"), (351, 2023, 100.0, "E")]


def normalized() -> pd.DataFrame:
    names = {code: (m49, name) for code, m49, name in AREAS}
    return pd.DataFrame([{"Area Code": a, "Area Code (M49)": names[a][0], "Area": names[a][1], **ID,
                          "Year": y, "Value": v, "Flag": f} for a, y, v, f in VALUES])


def wide() -> pd.DataFrame:
    rows = []
    for code, m49, name in AREAS:
        row = {"Area Code": code, "Area Code (M49)": m49, "Area": name, **ID}
        for year in (2022, 2023, 2030):
            match = [(v, f) for a, y, v, f in VALUES if a == code and y == year]
            row[f"Y{year}"], row[f"Y{year}F"] = match[0] if match else (None, None)
        rows.append(row)
    return pd.DataFrame(rows)


def test_both_layouts_give_the_same_table():
    a = tidy_faostat(normalized())
    b = tidy_faostat(wide())
    assert len(a) == len(b) == 5                         # empty cells of the wide layout are dropped
    columns = ["area_code", "year", "value", "flag", "iso3", "is_aggregate", "is_projection"]
    pd.testing.assert_frame_equal(a[columns].astype(str), b[columns].astype(str))


def test_country_codes_and_aggregates():
    df = tidy_faostat(normalized()).set_index(["area_code", "year"])
    assert df.loc[(171, 2023), "iso3"] == "PHL"          # M49 '608 -> ISO3 PHL
    assert df.loc[(171, 2023), "m49_code"] == "608"      # apostrophe removed
    assert df.loc[(5000, 2023), "is_aggregate"]          # World
    assert df.loc[(351, 2023), "is_aggregate"]           # 'China' = sum of 4 areas
    assert pd.isna(df.loc[(351, 2023), "iso3"])          # aggregates never get a country code
    assert not df.loc[(171, 2023), "is_aggregate"]


def test_projections_are_flagged():
    df = tidy_faostat(normalized()).set_index(["area_code", "year"])
    assert df.loc[(171, 2030), "is_projection"]          # flag F
    assert not df.loc[(171, 2023), "is_projection"]


def test_unexpected_file_is_rejected():
    with pytest.raises(DataQualityError, match="expected columns"):
        tidy_faostat(normalized().drop(columns=["Source"]))
