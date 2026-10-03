# Source profile: FAOSTAT Emissions Totals (domain GT)

- File: `Emissions_Totals_E_All_Data_(Normalized).zip` (20,501,708 bytes, SHA-256 `d2c47e116553711f...`), data file inside: `Emissions_Totals_E_All_Data_(Normalized).csv`
- Link: https://bulks-faostat.fao.org/production/Emissions_Totals_E_All_Data_(Normalized).zip
- **Retrieved:** 2026-10-03T14:31:14+00:00 (UTC), scripted download
- Layout: normalized (one row per area, item, element, source and year); shape as read: **2,500,090 rows x 15 columns**; values: **2,500,090**
- Years: 1961-2050; unit: kt
- Areas: 281 (242 countries and territories, 39 regions and groups); items: 44; elements: 9; sources: 2

## Columns
| column          | type     |   non_null |   missing |   missing_% |   unique | example                |
|:----------------|:---------|-----------:|----------:|------------:|---------:|:-----------------------|
| Area Code       | int64    |    2500090 |         0 |           0 |      281 | 2                      |
| Area Code (M49) | str      |    2500090 |         0 |           0 |      281 | '004                   |
| Area            | category |    2500090 |         0 |           0 |      281 | Afghanistan            |
| Item Code       | int64    |    2500090 |         0 |           0 |       44 | 5064                   |
| Item            | category |    2500090 |         0 |           0 |       44 | Crop Residues          |
| Element Code    | int64    |    2500090 |         0 |           0 |        9 | 7234                   |
| Element         | category |    2500090 |         0 |           0 |        9 | Direct emissions (N2O) |
| Year Code       | int64    |    2500090 |         0 |           0 |       65 | 1961                   |
| Year            | int64    |    2500090 |         0 |           0 |       65 | 1961                   |
| Source Code     | int64    |    2500090 |         0 |           0 |        2 | 3050                   |
| Source          | category |    2500090 |         0 |           0 |        2 | FAO TIER 1             |
| Unit            | category |    2500090 |         0 |           0 |        1 | kt                     |
| Value           | float64  |    2500090 |         0 |           0 |   949576 | 0.8762                 |
| Flag            | category |    2500090 |         0 |           0 |        3 | E                      |
| Note            | float64  |          0 |   2500090 |         100 |        0 |                        |

## Categories
Values per source and element:

| Source     | Element                              |   values |
|:-----------|:-------------------------------------|---------:|
| FAO TIER 1 | Direct emissions (N2O)               |   150434 |
| FAO TIER 1 | Emissions (CH4)                      |   315536 |
| FAO TIER 1 | Emissions (CO2)                      |   219065 |
| FAO TIER 1 | Emissions (CO2eq) (AR5)              |   457346 |
| FAO TIER 1 | Emissions (CO2eq) from CH4 (AR5)     |   314212 |
| FAO TIER 1 | Emissions (CO2eq) from F-gases (AR5) |    60632 |
| FAO TIER 1 | Emissions (CO2eq) from N2O (AR5)     |   380471 |
| FAO TIER 1 | Emissions (N2O)                      |   381795 |
| FAO TIER 1 | Indirect emissions (N2O)             |   134442 |
| UNFCCC     | Direct emissions (N2O)               |     5826 |
| UNFCCC     | Emissions (CH4)                      |    10732 |
| UNFCCC     | Emissions (CO2)                      |     7101 |
| UNFCCC     | Emissions (CO2eq) (AR5)              |    23118 |
| UNFCCC     | Emissions (CO2eq) from CH4 (AR5)     |     9088 |
| UNFCCC     | Emissions (CO2eq) from N2O (AR5)     |    13547 |
| UNFCCC     | Emissions (N2O)                      |    15272 |
| UNFCCC     | Indirect emissions (N2O)             |     1473 |

Flags:

| Flag   |   values |
|:-------|---------:|
| E      |  2432982 |
| A      |    45804 |
| F      |    21304 |

## Values
|       |       value (kt) |
|:------|-----------------:|
| count |      2.50009e+06 |
| mean  |  36935.7         |
| std   | 534645           |
| min   |     -1.24987e+07 |
| 25%   |      0.1708      |
| 50%   |     17.955       |
| 75%   |    899.051       |
| max   |      5.21057e+07 |

The part this project uses (FAO TIER 1, Emissions (CO2eq) (AR5), the 8 farm activities, from 2000, countries only): **35,412 values**, years 2000-2023. Per activity (kt CO2eq):

| Item                    |   values |     mean |   median |       max |
|:------------------------|---------:|---------:|---------:|----------:|
| Burning - Crop residues |     4385 |   187.45 |    25.01 |   6844.43 |
| Crop Residues           |     4426 |   916.38 |   113.17 |  34530.7  |
| Enteric Fermentation    |     4714 | 13697.5  |  2552.89 | 407857    |
| Manure Management       |     4738 |  1929.22 |   294.08 |  67234.8  |
| Manure applied to Soils |     4738 |   777.78 |   130.42 |  30814.2  |
| Manure left on Pasture  |     4738 |  3547.66 |   613.12 | 101034    |
| Rice Cultivation        |     2855 |  5648.72 |   236.75 | 151385    |
| Synthetic Fertilizers   |     4818 |  2762.54 |   138.63 | 170947    |

## Data-quality findings
1. **Totals mixed with countries**: 38 regions and groups (codes >= 5000, e.g. World, Asia, European Union) and 'China' (code 351, the sum of mainland China, Hong Kong, Macao and Taiwan) -> flagged `is_aggregate`, never added to country sums.
2. **Two sources**: FAO TIER 1 (2,413,933 values), UNFCCC (86,157 values) -> we use `FAO TIER 1`, FAO's own estimate that exists for every country.
3. **Several elements** (single gases and CO2-equivalents) -> we use `Emissions (CO2eq) (AR5)` (GWP-100 from IPCC AR5, the same as EDGAR).
4. **Projections mixed with data**: 21,304 values for 2030, 2050 with flag `F` -> flagged `is_projection`, never used as data.
5. **Areas without an ISO country code** (10): Belgium-Luxembourg (last year 1999), Channel Islands (last year 2023), Czechoslovakia (last year 1992), Ethiopia PDR (last year 1992), Netherlands Antilles (former) (last year 2010), Pacific Islands Trust Territory (last year 1990), Serbia and Montenegro (last year 2005), Sudan (former) (last year 2011), USSR (last year 1991), Yugoslav SFR (last year 1991). Only Serbia and Montenegro and Sudan (former) have values in the part we use -> mapped to EDGAR codes in config/faostat_area_mapping.csv.
6. **Negative emissions** where they are impossible (7 values in the 8 activities): Somalia / Synthetic Fertilizers, Timor-Leste / Synthetic Fertilizers -> rejected in the curated layer and listed in outputs/reports/faostat_rejected_rows.csv.
7. **Duplicate keys** (area, item, element, source, year): 0.
8. **M49 codes** are stored as text with a leading apostrophe (`'608`) -> cleaned in staging.
