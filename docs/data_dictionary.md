# Data dictionary

Curated files live in `data/curated/`; the same tables are loaded into PostgreSQL (schema `agri`).
Units: emissions in **Mt CO2eq** (million tonnes CO2-equivalent, GWP-100 from IPCC AR5), population in persons.

## `agri_country_year` (main data product)
One row per country and year. Parquet: `data/curated/agri_country_year.parquet`. Table: `agri.agri_country_year`.

| Field | Type | Nullable | Description | Example / allowed values |
|---|---|---|---|---|
| country_code | varchar(12) | no | EDGAR country code (primary key, part 1) | `PHL`, `SDN` |
| year | smallint | no | Calendar year (primary key, part 2) | 1970-2025 |
| co2_mt | double | yes | Agricultural CO2 (mainly urea and lime spread on fields), Mt CO2eq | 1.574 |
| ch4_mt | double | yes | Agricultural methane (livestock digestion, manure, rice), Mt CO2eq | 42.844 |
| n2o_mt | double | yes | Agricultural nitrous oxide (soils, manure, fertiliser), Mt CO2eq | 9.041 |
| total_mt | double | no | co2_mt + ch4_mt + n2o_mt | 53.459 |
| share_of_world_pct | double | no | Country's share of the world agricultural total that year, % | 0.847 |
| yoy_change_pct | double | yes | Change vs. the previous year, %; empty for the first year | -1.79 |
| population | bigint | yes | Population (World Bank); empty when the World Bank has no value | 115843670 |
| t_per_person | double | yes | total_mt x 1,000,000 / population, tonnes CO2eq per person | 0.461 |
| is_estimate | boolean | no | TRUE for EDGAR fast-track years (2023 onward in the 2026 edition) | true / false |
| edgar_edition | smallint | no | EDGAR edition the numbers come from | 2026 |
| batch_id | varchar(20) | no | (database only) pipeline run that loaded the row | `20261001T031500Z` |
| loaded_at | timestamptz | no | (database only) when the row was loaded | 2026-10-01 03:15:00+00 |

## `agri_emissions_by_gas` -> `agri.fact_emissions`
One row per country, gas and year.

| Field | Type | Nullable | Description | Example / allowed values |
|---|---|---|---|---|
| country_code | varchar(12) | no | EDGAR country code, FK to `dim_country` | `PHL` |
| gas / gas_code | varchar(10) | no | Gas, FK to `dim_gas` | `CO2`, `CH4`, `N2O` |
| year | smallint | no | Calendar year | 1970-2025 |
| emissions_mt_co2eq | double | no | Emissions, Mt CO2eq, >= 0 | 42.844 |
| is_estimate | boolean | no | EDGAR fast-track year | true |
| edgar_edition | smallint | no | EDGAR edition | 2026 |
| batch_id, loaded_at | varchar, timestamptz | no | (database only) load information | |

## `population` -> `agri.fact_population`
Population matched to EDGAR countries. For merged countries (e.g. `SDN` = Sudan + South Sudan) the
World Bank populations are added up, and a year is kept only if every part has a value.

| Field | Type | Nullable | Description | Example |
|---|---|---|---|---|
| country_code | varchar(12) | no | EDGAR country code, FK to `dim_country` | `SDN` |
| year | smallint | no | Calendar year | 2024 |
| population | bigint | no | Persons, > 0 | 62392371 |
| batch_id, loaded_at | varchar, timestamptz | no | (database only) load information | |

## `dim_country` -> `agri.dim_country`

| Field | Type | Nullable | Description | Example |
|---|---|---|---|---|
| country_code | varchar(12) | no | EDGAR code (primary key) | `ISR` |
| country_name | text | no | Name as written by EDGAR | Israel and Palestine, State of |
| wb_codes | text | no | World Bank codes whose population is used, separated by `;` | `ISR;PSE` |
| is_merged | boolean | no | TRUE when EDGAR combines several countries | true |

## `agri.dim_gas`

| Field | Type | Nullable | Description | Values |
|---|---|---|---|---|
| gas_code | varchar(10) | no | Primary key | CO2, CH4, N2O |
| gas_name | text | no | Full name | Carbon dioxide, Methane, Nitrous oxide |
| gwp100_ar5 | numeric(6,1) | no | 100-year warming factor used to convert tonnes of gas to CO2eq | 1, 28, 265 |

## `agri_emissions_by_activity` -> `agri.fact_emissions_by_activity` (FAOSTAT)
One row per country, farm activity and year, from FAOSTAT (FAO Tier 1 estimates, `Emissions (CO2eq) (AR5)`),
2000 to the latest FAOSTAT year (2023 in the October 2025 release). FAOSTAT areas are matched to EDGAR country
codes, so this table joins with every other table on `country_code`.

| Field | Type | Nullable | Description | Example / allowed values |
|---|---|---|---|---|
| country_code | varchar(12) | no | EDGAR country code, FK to `dim_country` | `PHL` |
| activity_code | integer | no | FAOSTAT item code, FK to `dim_activity` | 5060 |
| activity | text | no | (file only) activity name; in the database it is in `dim_activity` | Rice cultivation |
| activity_group | text | no | (file only) `Livestock` or `Crops` | Crops |
| year | smallint | no | Calendar year | 2000-2023 |
| emissions_mt_co2eq | double | no | Emissions, Mt CO2eq (FAOSTAT kt / 1,000), >= 0 | 45.114 |
| batch_id, loaded_at | varchar, timestamptz | no | (database only) load information | |

## `edgar_vs_faostat` -> `agri.edgar_vs_faostat`
EDGAR's agriculture total next to FAOSTAT's (sum of the 8 activities), for countries and years that both
sources have. The two use different methods, so a difference is expected; it is not an error.

| Field | Type | Nullable | Description | Example |
|---|---|---|---|---|
| country_code | varchar(12) | no | EDGAR country code, FK to `dim_country` | `PHL` |
| year | smallint | no | Calendar year | 2023 |
| edgar_total_mt | double | no | `agri_country_year.total_mt` (EDGAR: CO2 + CH4 + N2O), Mt CO2eq | 54.436 |
| faostat_total_mt | double | no | Sum of the 8 FAOSTAT activities, Mt CO2eq | 65.815 |
| difference_mt | double | no | faostat_total_mt - edgar_total_mt | 11.380 |
| difference_pct | double | yes | difference_mt / edgar_total_mt x 100; empty when EDGAR is 0 | 20.9 |
| batch_id, loaded_at | varchar, timestamptz | no | (database only) load information | |

## `dim_activity` -> `agri.dim_activity`

| Field | Type | Nullable | Description | Values |
|---|---|---|---|---|
| activity_code | integer | no | FAOSTAT item code (primary key) | 5058, 5059, 5060, 5061, 5062, 5063, 5064, 5066 |
| activity_name | text | no | Our name for the activity | Enteric fermentation, Manure management, Rice cultivation, Synthetic fertilizers, Manure applied to soils, Manure left on pasture, Crop residues, Burning crop residues |
| activity_group | text | no | `Livestock` (enteric fermentation and the three manure activities) or `Crops` (the other four) | Livestock, Crops |

## `agri.load_audit`

| Field | Type | Nullable | Description |
|---|---|---|---|
| audit_id | bigserial | no | Primary key |
| batch_id | varchar(20) | no | Pipeline run |
| table_name | text | no | Table that was loaded |
| rows_upserted | integer | no | Rows inserted or updated |
| rows_deleted | integer | no | Stale rows removed (from older batches) |
| loaded_at | timestamptz | no | When the load finished |

## Staging tables (for reference)

- `data/staging/edgar/` (Parquet, partitioned by `sector_key`): `country_code, country_name, country_type
  (country | aggregate | international), sector, sector_key, substance, gas (CO2 | CH4 | N2O | F-gases), year,
  emissions_mt_co2eq, is_estimate, edgar_edition`. All 8 sectors, all rows including `GLOBAL TOTAL` and `EU27`.
- `data/staging/worldbank/population.parquet`: `iso3, wb_name, year, population, is_country, indicator`.
- `data/staging/faostat/emissions_totals.parquet`: `area_code, m49_code, iso3, area, is_aggregate, item_code, item,
  element, source, unit, year, value, flag, is_projection`. Every FAOSTAT value (2,500,090 in the October 2025
  release): all areas including regions, all 44 items, 9 elements, both sources, 1961-2023 plus the 2030 and 2050
  projections. `value` is in kt; `iso3` is empty for regions, the 'China' total and former states.

## Reports written next to the curated layer

- `outputs/reports/faostat_unmatched_areas.csv`: FAOSTAT areas without an EDGAR code (small Pacific islands),
  with how many values and kt they had. They are not in the curated tables.
- `outputs/reports/faostat_rejected_rows.csv`: FAOSTAT values that are impossible (negative emissions), with the reason.
