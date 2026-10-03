# Database schema (ERD)

Schema `agri` in the `warehouse-db` PostgreSQL database. DDL: [`sql/01_schema.sql`](../sql/01_schema.sql).

```mermaid
erDiagram
    DIM_COUNTRY ||--o{ FACT_EMISSIONS : "has"
    DIM_GAS ||--o{ FACT_EMISSIONS : "has"
    DIM_COUNTRY ||--o{ FACT_POPULATION : "has"
    DIM_COUNTRY ||--o{ AGRI_COUNTRY_YEAR : "summarised in"
    DIM_COUNTRY ||--o{ FACT_EMISSIONS_BY_ACTIVITY : "has"
    DIM_ACTIVITY ||--o{ FACT_EMISSIONS_BY_ACTIVITY : "has"
    DIM_COUNTRY ||--o{ EDGAR_VS_FAOSTAT : "compared in"

    DIM_COUNTRY {
        varchar country_code PK "EDGAR code, e.g. PHL, SDN"
        text country_name
        text wb_codes "World Bank codes used for population, e.g. SDN;SSD"
        boolean is_merged
    }
    DIM_GAS {
        varchar gas_code PK "CO2, CH4, N2O"
        text gas_name
        numeric gwp100_ar5 "1, 28, 265"
    }
    DIM_ACTIVITY {
        integer activity_code PK "FAOSTAT item code, e.g. 5058"
        text activity_name "e.g. Enteric fermentation"
        text activity_group "Livestock or Crops"
    }
    FACT_EMISSIONS {
        varchar country_code PK, FK
        varchar gas_code PK, FK
        smallint year PK
        double emissions_mt_co2eq
        boolean is_estimate
        smallint edgar_edition
        varchar batch_id
        timestamptz loaded_at
    }
    FACT_POPULATION {
        varchar country_code PK, FK
        smallint year PK
        bigint population
        varchar batch_id
        timestamptz loaded_at
    }
    AGRI_COUNTRY_YEAR {
        varchar country_code PK, FK
        smallint year PK
        double co2_mt
        double ch4_mt
        double n2o_mt
        double total_mt
        double share_of_world_pct
        double yoy_change_pct
        bigint population
        double t_per_person
        boolean is_estimate
        smallint edgar_edition
        varchar batch_id
        timestamptz loaded_at
    }
    FACT_EMISSIONS_BY_ACTIVITY {
        varchar country_code PK, FK
        integer activity_code PK, FK
        smallint year PK
        double emissions_mt_co2eq
        varchar batch_id
        timestamptz loaded_at
    }
    EDGAR_VS_FAOSTAT {
        varchar country_code PK, FK
        smallint year PK
        double edgar_total_mt
        double faostat_total_mt
        double difference_mt
        double difference_pct
        varchar batch_id
        timestamptz loaded_at
    }
    LOAD_AUDIT {
        bigserial audit_id PK
        varchar batch_id
        text table_name
        integer rows_upserted
        integer rows_deleted
        timestamptz loaded_at
    }
```

## Keys and constraints

- **Primary keys** stop duplicates: `(country_code, gas_code, year)` for EDGAR emissions,
  `(country_code, activity_code, year)` for FAOSTAT emissions, and `(country_code, year)` for population, the
  country-year table and the comparison. They are also what `ON CONFLICT` uses when we UPSERT.
- **Foreign keys** stop orphan rows: every fact row must point to a country (and gas or activity) that exists.
  All three sources share one country list, `dim_country` (EDGAR codes), so they can be joined.
- **CHECK constraints** stop impossible values: negative emissions, population of 0, and years outside each
  table's range (from 1970 for EDGAR tables, 1960 for population, 1961 for FAOSTAT tables, up to 2100).
- **Index** on `year`, because most queries filter by year.
- `load_audit` is not linked to other tables; it is a log of every load (batch, table, rows).
