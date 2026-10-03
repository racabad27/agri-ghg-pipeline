from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

# The project root is the folder that contains src/, dags/, config/ ...
# Inside Docker it is /opt/airflow/project (PROJECT_ROOT is set in docker-compose.yml).
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[1]))

CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
CURATED_DIR = DATA_DIR / "curated"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
SQL_DIR = PROJECT_ROOT / "sql"


@lru_cache(maxsize=1)
def get_settings() -> dict:
    """Read config/pipeline.yaml once and reuse it."""
    with open(CONFIG_DIR / "pipeline.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_warehouse_settings() -> dict:
    """Connection details for our PostgreSQL warehouse. Nothing is hard-coded."""
    password = os.getenv("WAREHOUSE_DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "WAREHOUSE_DB_PASSWORD is not set. Copy .env.example to .env and fill it in."
        )
    return {
        "host": os.getenv("WAREHOUSE_DB_HOST", "localhost"),
        "port": int(os.getenv("WAREHOUSE_DB_PORT", "5433")),
        "dbname": os.getenv("WAREHOUSE_DB_NAME", "agri_dw"),
        "user": os.getenv("WAREHOUSE_DB_USER", "agri"),
        "password": password,
    }
