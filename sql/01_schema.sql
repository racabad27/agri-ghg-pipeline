-- Warehouse schema for the agricultural emissions pipeline (PostgreSQL 16).
-- Safe to run many times: every statement uses IF NOT EXISTS, so reruns change nothing.

CREATE SCHEMA IF NOT EXISTS agri;

-- Greenhouse gases and the AR5 100-year warming factors EDGAR uses
CREATE TABLE IF NOT EXISTS agri.dim_gas (
    gas_code    VARCHAR(10)  PRIMARY KEY,
    gas_name    TEXT         NOT NULL,
    gwp100_ar5  NUMERIC(6,1) NOT NULL CHECK (gwp100_ar5 > 0)
);

-- The 8 farm activities FAOSTAT reports (source: FAOSTAT item codes)
CREATE TABLE IF NOT EXISTS agri.dim_activity (
    activity_code   INTEGER PRIMARY KEY,             -- FAOSTAT item code, e.g. 5058
    activity_name   TEXT    NOT NULL,                -- e.g. Enteric fermentation
    activity_group  TEXT    NOT NULL CHECK (activity_group IN ('Livestock', 'Crops'))
);

-- One row per EDGAR country code
CREATE TABLE IF NOT EXISTS agri.dim_country (
    country_code  VARCHAR(12) PRIMARY KEY,           -- EDGAR code, e.g. PHL, SDN
    country_name  TEXT        NOT NULL,
    wb_codes      TEXT        NOT NULL,              -- World Bank codes used for population, e.g. 'SDN;SSD'
    is_merged     BOOLEAN     NOT NULL DEFAULT FALSE -- TRUE when EDGAR combines several countries
);

-- Agricultural emissions by country, gas and year (source: EDGAR)
CREATE TABLE IF NOT EXISTS agri.fact_emissions (
    country_code        VARCHAR(12)      NOT NULL REFERENCES agri.dim_country (country_code),
    gas_code            VARCHAR(10)      NOT NULL REFERENCES agri.dim_gas (gas_code),
    year                SMALLINT         NOT NULL CHECK (year BETWEEN 1970 AND 2100),
    emissions_mt_co2eq  DOUBLE PRECISION NOT NULL CHECK (emissions_mt_co2eq >= 0),
    is_estimate         BOOLEAN          NOT NULL,   -- TRUE for EDGAR fast-track years
    edgar_edition       SMALLINT         NOT NULL,
    batch_id            VARCHAR(20)      NOT NULL,   -- which pipeline run wrote this row
    loaded_at           TIMESTAMPTZ      NOT NULL,
    PRIMARY KEY (country_code, gas_code, year)
);

-- Population by EDGAR country and year (source: World Bank, merged countries added up)
CREATE TABLE IF NOT EXISTS agri.fact_population (
    country_code  VARCHAR(12) NOT NULL REFERENCES agri.dim_country (country_code),
    year          SMALLINT    NOT NULL CHECK (year BETWEEN 1960 AND 2100),
    population    BIGINT      NOT NULL CHECK (population > 0),
    batch_id      VARCHAR(20) NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (country_code, year)
);

-- Main data product: one row per country and year, ready for reports and dashboards
CREATE TABLE IF NOT EXISTS agri.agri_country_year (
    country_code        VARCHAR(12)      NOT NULL REFERENCES agri.dim_country (country_code),
    year                SMALLINT         NOT NULL CHECK (year BETWEEN 1970 AND 2100),
    co2_mt              DOUBLE PRECISION,
    ch4_mt              DOUBLE PRECISION,
    n2o_mt              DOUBLE PRECISION,
    total_mt            DOUBLE PRECISION NOT NULL CHECK (total_mt >= 0),
    share_of_world_pct  DOUBLE PRECISION NOT NULL,
    yoy_change_pct      DOUBLE PRECISION,
    population          BIGINT,
    t_per_person        DOUBLE PRECISION CHECK (t_per_person >= 0),
    is_estimate         BOOLEAN          NOT NULL,
    edgar_edition       SMALLINT         NOT NULL,
    batch_id            VARCHAR(20)      NOT NULL,
    loaded_at           TIMESTAMPTZ      NOT NULL,
    PRIMARY KEY (country_code, year)
);

-- Agricultural emissions by country, activity and year (source: FAOSTAT, FAO Tier 1, GWP-100 AR5)
CREATE TABLE IF NOT EXISTS agri.fact_emissions_by_activity (
    country_code        VARCHAR(12)      NOT NULL REFERENCES agri.dim_country (country_code),
    activity_code       INTEGER          NOT NULL REFERENCES agri.dim_activity (activity_code),
    year                SMALLINT         NOT NULL CHECK (year BETWEEN 1961 AND 2100),
    emissions_mt_co2eq  DOUBLE PRECISION NOT NULL CHECK (emissions_mt_co2eq >= 0),
    batch_id            VARCHAR(20)      NOT NULL,
    loaded_at           TIMESTAMPTZ      NOT NULL,
    PRIMARY KEY (country_code, activity_code, year)
);

-- EDGAR and FAOSTAT agriculture totals side by side (countries and years both sources have)
CREATE TABLE IF NOT EXISTS agri.edgar_vs_faostat (
    country_code      VARCHAR(12)      NOT NULL REFERENCES agri.dim_country (country_code),
    year              SMALLINT         NOT NULL CHECK (year BETWEEN 1961 AND 2100),
    edgar_total_mt    DOUBLE PRECISION NOT NULL,
    faostat_total_mt  DOUBLE PRECISION NOT NULL,
    difference_mt     DOUBLE PRECISION NOT NULL,   -- FAOSTAT minus EDGAR
    difference_pct    DOUBLE PRECISION,            -- empty when EDGAR is 0
    batch_id          VARCHAR(20)      NOT NULL,
    loaded_at         TIMESTAMPTZ      NOT NULL,
    PRIMARY KEY (country_code, year)
);

-- One row per table per pipeline run (what was loaded, when)
CREATE TABLE IF NOT EXISTS agri.load_audit (
    audit_id       BIGSERIAL   PRIMARY KEY,
    batch_id       VARCHAR(20) NOT NULL,
    table_name     TEXT        NOT NULL,
    rows_upserted  INTEGER     NOT NULL,
    rows_deleted   INTEGER     NOT NULL DEFAULT 0,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fact_emissions_year ON agri.fact_emissions (year);
CREATE INDEX IF NOT EXISTS idx_country_year_year ON agri.agri_country_year (year);
CREATE INDEX IF NOT EXISTS idx_by_activity_year ON agri.fact_emissions_by_activity (year);
