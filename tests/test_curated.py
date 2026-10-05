"""Tests for the curated layer: population matching and the country-year table."""
import pandas as pd
import pytest

from src.transform.curated import build_country_year, build_dim_country, population_for_edgar_countries

MAPPING = pd.DataFrame({"wb_code": ["SDN", "SSD"], "edgar_code": ["SDN", "SDN"]})
EMISSIONS = pd.DataFrame({
    "country_code": ["SDN", "SDN", "PHL", "PHL"],
    "country_name": ["Sudan and South Sudan"] * 2 + ["Philippines"] * 2,
    "gas": ["CH4", "N2O", "CH4", "N2O"],
    "year": [2024] * 4,
    "emissions_mt_co2eq": [60.0, 30.0, 40.0, 10.0],
    "is_estimate": [True] * 4,
    "edgar_edition": [2026] * 4,
})
POPULATION = pd.DataFrame({
    "iso3": ["SDN", "SSD", "PHL", "SDN"],
    "year": [2024, 2024, 2024, 2023],
    "population": [50_000_000, 10_000_000, 100_000_000, 49_000_000],
    "is_country": [True] * 4,
})


def test_merged_countries_add_up_population():
    dim = build_dim_country(EMISSIONS, MAPPING)
    assert dim.set_index("country_code").loc["SDN", "wb_codes"] == "SDN;SSD"
    pop = population_for_edgar_countries(POPULATION, dim).set_index(["country_code", "year"])
    assert pop.loc[("SDN", 2024), "population"] == 60_000_000  # Sudan + South Sudan


def test_merged_country_needs_every_part():
    dim = build_dim_country(EMISSIONS, MAPPING)
    pop = population_for_edgar_countries(POPULATION, dim)
    # 2023 only has Sudan, not South Sudan -> no population for SDN in 2023
    assert pop[(pop["country_code"] == "SDN") & (pop["year"] == 2023)].empty


def test_country_year_totals_per_person_and_shares():
    dim = build_dim_country(EMISSIONS, MAPPING)
    pop = population_for_edgar_countries(POPULATION, dim)
    by_gas = EMISSIONS.drop(columns="country_name")
    cy = build_country_year(by_gas, pop, edition=2026).set_index("country_code")
    assert cy.loc["PHL", "total_mt"] == 50.0
    assert cy.loc["PHL", "t_per_person"] == pytest.approx(0.5)       # 50 Mt / 100 million people
    assert cy["share_of_world_pct"].sum() == pytest.approx(100.0)
    assert cy.loc["SDN", "share_of_world_pct"] == pytest.approx(64.2857, rel=1e-4)  # 90 of 140 Mt
