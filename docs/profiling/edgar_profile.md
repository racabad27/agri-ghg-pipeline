# Source profile: EDGAR 2026 (sheet `GHG_by_sector_and_country`)

- File: `EDGAR_2026_GHG_booklet_2026.xlsx` (4,767,596 bytes, SHA-256 `bb77a0da5735925b...`)
- Link: https://edgar.jrc.ec.europa.eu/booklet/EDGAR_2026_GHG_booklet_2026.xlsx
- **Retrieved:** 2026-10-03T12:47:48+00:00 (UTC), scripted download
- Shape as read: **4,858 rows x 60 columns** (4 ID columns + 56 year columns 1970-2025)
- Layout: wide (one column per year). Unit: Mt CO2eq per year (GWP-100, IPCC AR5).

## ID columns
| column             | type   |   non_null |   missing |   missing_% |   unique | example     |
|:-------------------|:-------|-----------:|----------:|------------:|---------:|:------------|
| Substance          | str    |       4856 |         2 |        0.04 |        4 | CO2         |
| Sector             | str    |       4856 |         2 |        0.04 |        8 | Agriculture |
| EDGAR Country Code | str    |       4856 |         2 |        0.04 |      212 | AFG         |
| Country            | str    |       4856 |         2 |        0.04 |      212 | Afghanistan |

## Year columns (values)
- Cells: 272,048; missing: 5,501 (2.02%); zeros: 1,539; negatives: 0
- Missing cells per year: min 67, max 120

Descriptive statistics of all emission values (Mt CO2eq):

|       |       value |
|:------|------------:|
| count | 266547      |
| mean  |     16.5413 |
| std   |    218.733  |
| min   |      0      |
| 25%   |      0.005  |
| 50%   |      0.0872 |
| 75%   |      1.3137 |
| max   |  15703.4    |

Agriculture, countries only (the part this project uses), per gas (Mt CO2eq):

| Substance       |   values |    mean |   median |      max |
|:----------------|---------:|--------:|---------:|---------:|
| CO2             |     5825 |  0.9943 |   0.1775 |  32.2028 |
| GWP_100_AR5_CH4 |    11389 | 17.8838 |   3.0028 | 594.51   |
| GWP_100_AR5_N2O |    11391 |  6.756  |   1.2947 | 272.436  |

## Categories
Rows per sector:

| Sector                |   rows |
|:----------------------|-------:|
| Processes             |    671 |
| Transport             |    633 |
| Buildings             |    629 |
| Power Industry        |    627 |
| Industrial Combustion |    624 |
| Fuel Production       |    608 |
| Waste                 |    538 |
| Agriculture           |    526 |

Rows per substance, and missing cells per substance:

| Substance           |   rows |   missing_cells |
|:--------------------|-------:|----------------:|
| GWP_100_AR5_N2O     |   1664 |             912 |
| GWP_100_AR5_CH4     |   1558 |            1460 |
| CO2                 |   1483 |            2712 |
| GWP_100_AR5_F-gases |    151 |             305 |

## Data-quality findings
1. **2 completely blank rows** inside the sheet (separators) -> dropped in staging.
2. **Duplicate keys** (substance, sector, country): 0.
3. **Totals mixed with countries**: `GLOBAL TOTAL` and `EU27` rows -> flagged as aggregates, excluded from country sums.
4. **6 codes are not ISO 3166 country codes**: SCG (Serbia and Montenegro), ANT (Curaçao), AIR (International Aviation), SEA (International Shipping), EU27 (EU27), GLOBAL TOTAL (GLOBAL TOTAL).
5. **Merged countries** (one code covers several countries): CHE = Switzerland and Liechtenstein, ESP = Spain and Andorra, FRA = France and Monaco, ISR = Israel and Palestine, State of, ITA = Italy, San Marino and the Holy See, SCG = Serbia and Montenegro, SDN = Sudan and South Sudan.
6. **Missing values** are empty cells, not zeros -> kept as 'no estimate' (dropped), never filled with 0.
7. **Estimates**: years >= 2023 are EDGAR fast-track estimates -> `is_estimate` flag.
