# Source profile: World Bank API, indicator `SP.POP.TOTL` (population)

- Pull folder: `data/raw/worldbank/SP.POP.TOTL/pulled=2026-10-03` (18 pages, 17,490 records)
- **Retrieved:** 2026-10-03T14:10:07+00:00 (UTC), scripted API calls
- Source last updated: 2026-07-13
- Shape after flattening: **17,490 rows x 4 fields** (`countryiso3code`, `country_name`, `date`, `value`; `year` is derived from `date`)
- Years: 1960-2025; codes: 261 (217 countries/territories, 44 regions or income groups)

## Columns
| column          | type    |   non_null |   missing |   missing_% |   unique | example                     |
|:----------------|:--------|-----------:|----------:|------------:|---------:|:----------------------------|
| countryiso3code | str     |      17490 |         0 |        0    |      261 | AFE                         |
| country_name    | str     |      17490 |         0 |        0    |      265 | Africa Eastern and Southern |
| date            | str     |      17490 |         0 |        0    |       66 | 2025                        |
| value           | float64 |      17394 |        96 |        0.55 |    17194 | 788844284.0                 |

## Values
|       |      population |
|:------|----------------:|
| count | 17394           |
| mean  |     2.19715e+08 |
| std   |     7.24372e+08 |
| min   |  2715           |
| 25%   |     1.01095e+06 |
| 50%   |     6.75814e+06 |
| 75%   |     4.61611e+07 |
| max   |     8.21542e+09 |

Records with a value in the latest 5 years: 2021: 264, 2022: 264, 2023: 264, 2024: 264, 2025: 264

## Data-quality findings
1. **Regions and income groups are mixed with countries** (44 codes, e.g. , AFE, AFW, ARB, CEB, CSS, EAP, EAR) -> flagged with `is_country = False`, never joined to countries.
2. **Missing values**: 96 records have no value -> dropped in staging.
3. **Duplicates** (code, year): 264.
4. **Types**: `date` arrives as text -> converted to integer year; `value` to whole numbers.
5. **Different country lists**: EDGAR merges some countries (e.g. Sudan + South Sudan); config/country_mapping.csv adds their populations up.
