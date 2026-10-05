# Data flow and lineage

```mermaid
flowchart TD
    E1["EDGAR website<br/>EDGAR_2026_GHG_booklet_2026.xlsx"] -->|extract_edgar: HTTP download, zip + sheet check| R1["data/raw/edgar/edition=2026/<br/>EDGAR_2026_GHG_booklet_2026.xlsx<br/>+ .meta.json"]
    W1["World Bank API<br/>SP.POP.TOTL, 1,000 records per page"] -->|extract_worldbank: page by page, retries| R2["data/raw/worldbank/SP.POP.TOTL/pulled=YYYY-MM-DD/<br/>page_001.json ... + _manifest.json"]
    F1["FAOSTAT bulk download<br/>Emissions_Totals_E_All_Data_(Normalized).zip"] -->|extract_faostat: HTTP download, zip check| R3["data/raw/faostat/pulled=YYYY-MM-DD/<br/>...(Normalized).zip + .meta.json"]

    R1 -->|stage_edgar: drop blank rows, wide to long,<br/>types, gas codes, country types, is_estimate| S1["data/staging/edgar/sector_key=*/<br/>Parquet, 8 sector folders"]
    R2 -->|stage_worldbank: flatten JSON, types,<br/>drop empty values, flag regions| S2["data/staging/worldbank/population.parquet"]
    R3 -->|stage_faostat: read CSV from zip, types, M49 to ISO3,<br/>flag regions + China total + projections| S3["data/staging/faostat/emissions_totals.parquet"]

    S1 -->|validate_edgar: 9 checks| S1
    S2 -->|validate_worldbank: 7 checks| S2
    S3 -->|validate_faostat: 10 checks| S3

    S1 -->|build_curated: read ONLY sector_key=agriculture,<br/>countries only, CO2/CH4/N2O| C1["data/curated/agri_emissions_by_gas.parquet"]
    S1 --> C2["data/curated/dim_country.parquet"]
    M["config/country_mapping.csv<br/>(merged countries)"] --> C2
    S2 -->|add up populations of merged countries| C3["data/curated/population.parquet"]
    C1 --> C4["data/curated/agri_country_year.parquet<br/>(main data product)"]
    C3 --> C4
    C4 -->|compare_formats| X["data/curated/exports/<br/>.csv .json .parquet"]

    S3 -->|build_faostat_curated: FAO Tier 1, CO2eq AR5,<br/>8 activities, from 2000, countries only, kt to Mt| C5["data/curated/agri_emissions_by_activity.parquet"]
    FM["config/faostat_area_mapping.csv<br/>+ country_mapping.csv"] --> C5
    C2 -->|only EDGAR countries| C5
    C5 -.->|left out, with the reason| Q["outputs/reports/<br/>faostat_unmatched_areas.csv<br/>faostat_rejected_rows.csv"]
    C5 --> C6["data/curated/edgar_vs_faostat.parquet"]
    C4 --> C6
    C5 --> C7["data/curated/dim_activity.parquet"]

    C1 -->|load_warehouse: UPSERT| D1[("agri.fact_emissions")]
    C2 --> D2[("agri.dim_country")]
    C3 --> D3[("agri.fact_population")]
    C4 --> D4[("agri.agri_country_year")]
    C5 --> D6[("agri.fact_emissions_by_activity")]
    C6 --> D7[("agri.edgar_vs_faostat")]
    C7 --> D8[("agri.dim_activity")]
    D1 & D2 & D3 & D4 & D6 & D7 & D8 --> D5[("agri.load_audit<br/>one row per table per run,<br/>same transaction")]
    D1 & D3 & D4 & D6 & D7 --> K{{"check_warehouse:<br/>row counts = files, world total, no orphans"}}
    K --> V["outputs/validation/warehouse.json"]
```

## What each layer is allowed to do

| Layer | Allowed | Not allowed |
|---|---|---|
| Raw | Save the file exactly as received; add a metadata file next to it | Editing, renaming columns, deleting rows |
| Staging | Drop empty rows, reshape wide to long, fix types, trim text, map codes, add flags | Filtering the scope (all sectors and all countries stay), joining other sources |
| Curated | Filter to agriculture and real countries, join population, compute totals, shares, growth, per-person; match FAOSTAT areas to EDGAR countries, convert kt to Mt, set aside impossible rows (with a report) | Changing source values |
| Warehouse | Upsert curated rows, delete stale rows from older batches, write the audit table | Any transformation (the database mirrors the curated files) |

## Tracing one record through the pipeline (demo)

Philippines, methane from agriculture, 2024:

1. **Raw**: open `data/raw/edgar/edition=2026/EDGAR_2026_GHG_booklet_2026.xlsx`, sheet
   `GHG_by_sector_and_country`, the row `GWP_100_AR5_CH4 | Agriculture | PHL`, column `2024`.
2. **Staging**:
   ```bash
   docker compose exec airflow-scheduler python -c "import pandas as pd; df = pd.read_parquet('data/staging/edgar', filters=[('sector_key','==','agriculture')]); print(df.query(\"country_code=='PHL' and gas=='CH4' and year==2024\"))"
   ```
3. **Curated**:
   ```bash
   docker compose exec airflow-scheduler python -c "import pandas as pd; df = pd.read_parquet('data/curated/agri_emissions_by_gas.parquet'); print(df.query(\"country_code=='PHL' and gas=='CH4' and year==2024\"))"
   ```
4. **Warehouse**:
   ```bash
   docker compose exec warehouse-db psql -U agri -d agri_dw -c "SELECT * FROM agri.fact_emissions WHERE country_code='PHL' AND gas_code='CH4' AND year=2024;"
   ```

The value is the same at every step, and `batch_id` / `loaded_at` show which run wrote it.

### The same for FAOSTAT: Philippines, rice cultivation, 2023

1. **Raw**: the zip in `data/raw/faostat/pulled=<date>/`; inside the CSV, the row with area code `171`
   (Philippines), item `Rice Cultivation`, element `Emissions (CO2eq) (AR5)`, source `FAO TIER 1`, year `2023`
   (value in kt).
2. **Staging**:
   ```bash
   docker compose exec airflow-scheduler python -c "import pandas as pd; df = pd.read_parquet('data/staging/faostat/emissions_totals.parquet', filters=[('area_code','==',171),('item_code','==',5060),('year','==',2023)]); print(df)"
   ```
3. **Curated** (kt / 1,000 = Mt):
   ```bash
   docker compose exec airflow-scheduler python -c "import pandas as pd; df = pd.read_parquet('data/curated/agri_emissions_by_activity.parquet'); print(df.query(\"country_code=='PHL' and activity_code==5060 and year==2023\"))"
   ```
4. **Warehouse**:
   ```bash
   docker compose exec warehouse-db psql -U agri -d agri_dw -c "SELECT * FROM agri.fact_emissions_by_activity WHERE country_code='PHL' AND activity_code=5060 AND year=2023;"
   ```
