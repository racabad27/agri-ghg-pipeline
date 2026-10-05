# Source inventory

| | EDGAR (emissions) | World Bank (population) | FAOSTAT (emissions by activity) |
|---|---|---|---|
| **Provider** | European Commission, Joint Research Centre (JRC): Emissions Database for Global Atmospheric Research | World Bank: World Development Indicators (WDI) | Food and Agriculture Organization of the UN (FAO), Statistics Division: FAOSTAT domain *Emissions Totals* (GT) |
| **What we use** | Sheet `GHG_by_sector_and_country`, all 8 sectors (curated layer keeps Agriculture) | Indicator `SP.POP.TOTL` (population, total) | The whole file in staging; the curated layer keeps FAO Tier 1, `Emissions (CO2eq) (AR5)`, the 8 farm activities, 2000 onward |
| **Link / endpoint** | Report page: https://edgar.jrc.ec.europa.eu/report_2026 <br> File: https://edgar.jrc.ec.europa.eu/booklet/EDGAR_2026_GHG_booklet_2026.xlsx | https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=1000&page=N | Domain page: https://www.fao.org/faostat/en/#data/GT <br> File: https://bulks-faostat.fao.org/production/Emissions_Totals_E_All_Data_(Normalized).zip <br> Catalogue of all bulk files: https://bulks-faostat.fao.org/production/datasets_E.xml |
| **Source type / format** | File download, Excel workbook (.xlsx, 8 sheets, about 4.8 MB) | REST API, JSON, paged (1,000 records per page) | Bulk file download: zip (about 20 MB) with one CSV (about 325 MB, UTF-8), normalized layout (one row per value) |
| **Coverage** | 208 countries and territories + 4 other codes (`GLOBAL TOTAL`, `EU27`, `AIR`, `SEA`), 1970-2025, CO2 / CH4 / N2O / F-gases | 217 countries + 48 regions and income groups, 1960-latest | 242 countries and territories (including former states) + 38 regions and groups + the 'China' total, 1961-2023 plus projections for 2030 and 2050 |
| **Volume** | 4,858 sheet rows x 60 columns = 266,547 non-empty values (long format) | About 17,500 records | 2,500,090 rows (release of 28 October 2025) |
| **Update frequency** | One edition per year; recent years are revised in the next edition | Several updates per year (see `source_last_updated` in `_manifest.json`) | Once a year (the October 2025 release covers up to 2023); each release can revise earlier years |
| **Access date** | Written by the download step (`data/raw/edgar/edition=2026/*.meta.json`) and shown as **Retrieved** at the top of [the EDGAR profile](profiling/edgar_profile.md) | Written by the API step (`data/raw/worldbank/SP.POP.TOTL/pulled=*/_manifest.json`) and shown as **Retrieved** at the top of [the World Bank profile](profiling/worldbank_profile.md) | Written by the download step (`data/raw/faostat/pulled=*/*.meta.json`) and shown as **Retrieved** at the top of [the FAOSTAT profile](profiling/faostat_profile.md) |
| **Retrieval method** | Scripted HTTP download (`src/extract/edgar.py`): retries, size check, zip + sheet check, SHA-256 | Scripted API calls (`src/extract/worldbank.py`): all pages, retries, record-count check | Scripted HTTP download (`src/extract/faostat.py`): retries, size check, zip test + data CSV check, SHA-256 |
| **License / terms** | CC BY 4.0 (European Union material). The fuel-combustion CO2 part (IEA-EDGAR CO2, not agriculture) is CC BY-NC-ND 4.0, so we do not publish derived non-agriculture data. | CC BY 4.0 | CC BY 4.0 (FAO statistical database terms of use: https://www.fao.org/contact-us/terms/db-terms-of-use/en/) |
| **Citation** | Crippa, M., Guizzardi, D., Pagani, F., Banja, M., Ciarlantini, S. et al., *GHG emissions of all world countries - 2026 Report*, Publications Office of the European Union, 2026, doi:10.2760/7717504, JRC147815. Data: EDGAR Community GHG Database version EDGAR_2026_GHG (2026), https://edgar.jrc.ec.europa.eu/report_2026. | The World Bank: World Development Indicators: Population, total (SP.POP.TOTL). | FAO. 2025. FAOSTAT: Emissions Totals. Accessed on *(2026-10-03T14:31:14+00:00 in UTC)*. https://www.fao.org/faostat/en/#data/GT. Licence: CC-BY-4.0. |

**Why the EDGAR "booklet" file:** it is EDGAR's official country-by-sector table (the numbers behind the EDGAR 2026
report): one Excel file with every country, sector, gas and year from 1970 to 2025. Our questions need national
totals per sector and year, so this is the right level of detail. We keep the file byte-for-byte in the raw
layer and do all cleaning in our own pipeline (blank rows, totals, merged countries, estimates).

## Known limitations and risks

**EDGAR**
- 2023-2025 are **fast-track estimates** (flagged `is_estimate`), not final values.
- **Agriculture is one aggregated sector**: no split into livestock, rice, fertiliser.
- **Totals mixed with countries** (`GLOBAL TOTAL`, `EU27`) and **merged countries** (e.g. `SDN` = Sudan + South Sudan,
  `ISR` = Israel + Palestine, `SCG` = Serbia + Montenegro); see `config/country_mapping.csv`.
- **Old or non-ISO codes**: `ANT` is used for Curaçao; `AIR` / `SEA` are international aviation and shipping.
- The file name contains the edition year, so the link changes every year (it is a setting in `config/pipeline.yaml`).
- Some places are listed separately from France (Réunion, Guadeloupe, Martinique, French Guiana), while the World
  Bank includes them in France's population.

**FAOSTAT**
- **Ends in 2023** (October 2025 release), two years before EDGAR; the comparison only covers 2000-2023.
- **Totals mixed with countries**: 38 regions and groups (codes >= 5000) and 'China' (code 351 = mainland + Hong Kong +
  Macao + Taiwan) -> flagged `is_aggregate`; the staging checks prove World = sum of countries and China = its 4 parts.
- **Two sources in one file**: FAO's own Tier 1 estimates and country reports to the UNFCCC. We use FAO Tier 1,
  because it exists for every country and year.
- **Projections** for 2030 and 2050 (flag `F`) sit next to real data -> flagged `is_projection` and never used.
- **Former states** (USSR, Yugoslav SFR, Czechoslovakia, Sudan (former), Serbia and Montenegro, ...) have M49 codes that
  are not ISO codes. From 2000 only Sudan (former) and Serbia and Montenegro remain, and EDGAR merges both, so
  `config/faostat_area_mapping.csv` maps them to `SDN` and `SCG`.
- **Small areas EDGAR does not list** (Marshall Islands, Micronesia, Nauru, Niue, Palau, Tokelau, Tuvalu): left out and
  listed in `outputs/reports/faostat_unmatched_areas.csv` (less than 0.01% of the world total).
- **7 negative values** for synthetic fertilizers (Somalia, Timor-Leste), which is impossible: rejected in the curated
  layer and listed in `outputs/reports/faostat_rejected_rows.csv`.
- **Different method from EDGAR** (FAO Tier 1 vs EDGAR's own inventory): the world totals differ by about 4-6%, and some
  countries by much more. We compare them in `edgar_vs_faostat` and never add them together.

**World Bank**
- **Regions and income groups** are mixed with countries (48 codes such as `WLD`, `EAS`); we flag them with `is_country`.
- Some places have no World Bank population (e.g. Taiwan), so their emissions per person are empty.
- Palestine starts in 1990, so Israel + Palestine has a population only from 1990.
- The latest year can be missing for some countries until the World Bank publishes it.

## Profiling reports

Generated by `scripts/profile_sources.py` from the raw files (row and column counts, types, missing values,
duplicates, unique values, year ranges, statistics, quality findings):

- [EDGAR profile](profiling/edgar_profile.md)
- [World Bank profile](profiling/worldbank_profile.md)
- [FAOSTAT profile](profiling/faostat_profile.md)
