# Data contracts: `agri_country_year` and `agri_emissions_by_activity`

These contracts describe what consumers of our data products can rely on. Every rule below is checked
automatically, by a validation task of the pipeline or by a constraint in PostgreSQL (the `enforced_by` field).
If a check before the load fails, the load does not run. `check_warehouse` runs after the load and turns the
run red if the database and the files differ. `required: false` means the value may be empty (NULL).

## 1. Main data product: `agri_country_year`

```yaml
contract:
  name: agri_country_year
  owner: Group Delta (DSS150P Data Engineering)
  description: >
    Agricultural greenhouse-gas emissions per country and year (CO2, CH4, N2O in Mt CO2eq),
    with totals, share of the world, yearly change, population and emissions per person.
  producer:
    pipeline: Airflow DAG agri_emissions_pipeline
    tasks: [build_curated, validate_curated, load_warehouse]
    sources:
      - EDGAR 2026, European Commission JRC (sheet GHG_by_sector_and_country, sector Agriculture)
      - World Bank World Development Indicators API, indicator SP.POP.TOTL
  consumers:
    - Policy analysts comparing countries (for example the Philippines and ASEAN neighbours)
    - Our analysis notebook and SQL reports
  locations:
    file: data/curated/agri_country_year.parquet
    database_table: agri.agri_country_year (PostgreSQL, database agri_dw)
  refresh:
    schedule: monthly (Airflow @monthly); new EDGAR edition once a year
    freshness: data is at most one monthly run old after a successful run
  grain: one row per country_code and year
  primary_key: [country_code, year]
  schema:
    - {name: country_code,       type: varchar(12), required: true,  nullable: false, constraint: "exists in dim_country"}
    - {name: year,               type: smallint,    required: true,  nullable: false, constraint: "1970 <= year <= 2100"}
    - {name: co2_mt,             type: double,      required: false, nullable: true,  constraint: ">= 0"}
    - {name: ch4_mt,             type: double,      required: false, nullable: true,  constraint: ">= 0"}
    - {name: n2o_mt,             type: double,      required: false, nullable: true,  constraint: ">= 0"}
    - {name: total_mt,           type: double,      required: true,  nullable: false, constraint: ">= 0"}
    - {name: share_of_world_pct, type: double,      required: true,  nullable: false, constraint: "sums to 100 per year"}
    - {name: yoy_change_pct,     type: double,      required: false, nullable: true}
    - {name: population,         type: bigint,      required: false, nullable: true,  constraint: "> 0"}
    - {name: t_per_person,       type: double,      required: false, nullable: true,  constraint: "0 <= value <= 100"}
    - {name: is_estimate,        type: boolean,     required: true,  nullable: false}
    - {name: edgar_edition,      type: smallint,    required: true,  nullable: false}
  quality_rules:
    - {rule: "no duplicate (country_code, year)",                       enforced_by: "validate_curated + PRIMARY KEY"}
    - {rule: "total_mt, country_code, year, share never empty",         enforced_by: "validate_curated + NOT NULL"}
    - {rule: "every country_code exists in dim_country",               enforced_by: "validate_curated + FOREIGN KEY"}
    - {rule: "no negative emissions (gases and total)",                 enforced_by: "validate_edgar (every value >= 0) + validate_curated (total) + CHECK (total)"}
    - {rule: "population > 0",                                          enforced_by: "validate_worldbank + CHECK on fact_population"}
    - {rule: "t_per_person between 0 and 100 tonnes",                   enforced_by: "validate_curated"}
    - {rule: ">= 99% of emissions have a population (years with data)", enforced_by: "validate_curated"}
    - {rule: "shares add up to 100% every year",                        enforced_by: "validate_curated"}
    - {rule: "database row count = file row count",                     enforced_by: "check_warehouse"}
  change_policy: >
    Adding a column = minor version (1.1.0). Renaming or removing a column, or changing a type or the
    grain = major version (2.0.0), announced to consumers first.
  known_limitations:
    - 2023-2025 values are EDGAR fast-track estimates (is_estimate = true) and will be revised.
    - Agriculture is one aggregated sector in EDGAR; the split by activity is in agri_emissions_by_activity (FAOSTAT).
    - Merged countries (e.g. SDN = Sudan + South Sudan) cannot be split.
    - No population for places the World Bank does not report separately (e.g. Taiwan, Réunion).
```

## 2. Activity breakdown: `agri_emissions_by_activity`

```yaml
contract:
  name: agri_emissions_by_activity
  owner: Group Delta (DSS150P Data Engineering)
  description: >
    Agricultural greenhouse-gas emissions per country, farm activity and year (Mt CO2eq), from FAOSTAT,
    matched to the same EDGAR country codes as agri_country_year.
  producer:
    pipeline: Airflow DAG agri_emissions_pipeline
    tasks: [build_faostat_curated, validate_curated, load_warehouse]
    sources:
      - FAOSTAT Emissions Totals (FAO), source FAO TIER 1, element Emissions (CO2eq) (AR5)
  consumers:
    - Analysts asking which activities (livestock, rice, fertiliser, ...) drive a country's emissions
    - Our analysis notebook and SQL reports
  locations:
    file: data/curated/agri_emissions_by_activity.parquet
    database_table: agri.fact_emissions_by_activity (names and groups in agri.dim_activity)
  refresh:
    schedule: monthly (Airflow @monthly); FAOSTAT publishes a new release about once a year
  grain: one row per country_code, activity_code and year
  primary_key: [country_code, activity_code, year]
  schema:
    - {name: country_code,       type: varchar(12), required: true, nullable: false, constraint: "exists in dim_country"}
    - {name: activity_code,      type: integer,     required: true, nullable: false, constraint: "one of the 8 codes in dim_activity"}
    - {name: activity,           type: text,        required: true, nullable: false}
    - {name: activity_group,     type: text,        required: true, nullable: false, constraint: "Livestock or Crops"}
    - {name: year,               type: smallint,    required: true, nullable: false, constraint: "2000 <= year (the curated step keeps only these years)"}
    - {name: emissions_mt_co2eq, type: double,      required: true, nullable: false, constraint: ">= 0"}
  quality_rules:
    - {rule: "no duplicate (country_code, activity_code, year)",           enforced_by: "validate_curated + PRIMARY KEY"}
    - {rule: "every country_code exists in dim_country",                  enforced_by: "validate_curated + FOREIGN KEY"}
    - {rule: "only the 8 known activities",                               enforced_by: "validate_curated + FOREIGN KEY"}
    - {rule: "no negative emissions (impossible rows are rejected)",       enforced_by: "validate_curated + CHECK"}
    - {rule: ">= 99.5% of FAOSTAT's country emissions are matched",        enforced_by: "validate_curated"}
    - {rule: "the 8 activities add up to FAOSTAT's own subtotals",         enforced_by: "validate_faostat"}
    - {rule: "world total within 15% of EDGAR's every year",              enforced_by: "validate_curated"}
    - {rule: "database row count = file row count",                       enforced_by: "check_warehouse"}
  change_policy: same as agri_country_year
  known_limitations:
    - Ends two years earlier than EDGAR (2023 in the October 2025 release).
    - FAO Tier 1 method; totals differ from EDGAR (about 4-6% at world level). Do not add the two sources together.
    - Small Pacific islands without an EDGAR code are not included (listed in outputs/reports/faostat_unmatched_areas.csv).
```
