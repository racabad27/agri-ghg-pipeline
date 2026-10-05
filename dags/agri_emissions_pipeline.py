from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow.sdk import Param, dag, get_current_context, task
from airflow.sdk.exceptions import AirflowFailException


def log_failure(context) -> None:
    """Runs once a task has failed for good (after its retries): one clear line to look for in the log."""
    ti = context["ti"]
    logging.getLogger("airflow.task").error(
        "PIPELINE FAILED at task %s (run %s, try %s): %s",
        ti.task_id, context["run_id"], ti.try_number, context.get("exception"))


def checks_passed(run_checks) -> bool:
    """Run a set of data-quality checks. A failed check fails the task at once, without retries,
    because the same data would fail again."""
    from src.utils.errors import DataQualityError

    try:
        return run_checks()["passed"]
    except DataQualityError as err:
        raise AirflowFailException(str(err)) from err


DEFAULT_ARGS = {
    "owner": "group-delta",
    "retries": 2,                                # try a failed task 2 more times (network, database)
    "retry_delay": timedelta(minutes=1),         # wait 1 minute between tries
    "execution_timeout": timedelta(minutes=30),  # stop a task that hangs
    "on_failure_callback": log_failure,          # clear message when a task has failed for good
}


@dag(
    dag_id="agri_emissions_pipeline",
    description="EDGAR + World Bank + FAOSTAT agricultural emissions: raw -> staging -> curated -> PostgreSQL",
    schedule="@monthly",   # the World Bank updates several times a year, EDGAR and FAOSTAT once a year
    start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Manila"),
    catchup=False,         # do not run for past months
    max_active_runs=1,     # never two runs writing the same files at once
    default_args=DEFAULT_ARGS,
    params={
        "edgar_edition": Param(2026, type="integer", minimum=2024, description="EDGAR edition (year in the file name)"),
        "force_download": Param(False, type="boolean", description="Download again even if raw files exist"),
    },
    tags=["dss150p", "edgar", "worldbank", "faostat", "agriculture"],
    doc_md=__doc__,
)
def agri_emissions_pipeline():
    # Imports of our own code happen inside each task, so Airflow can read this file quickly.

    @task
    def extract_edgar() -> str:
        from src.extract.edgar import extract_edgar as run

        params = get_current_context()["params"]
        return run(edition=params["edgar_edition"], force=params["force_download"])

    @task
    def extract_worldbank() -> str:
        from src.extract.worldbank import extract_worldbank as run

        return run(force=get_current_context()["params"]["force_download"])

    @task
    def extract_faostat() -> str:
        from src.extract.faostat import extract_faostat as run

        return run(force=get_current_context()["params"]["force_download"])

    @task
    def stage_edgar(raw_path: str) -> str:
        from src.transform.edgar import stage_edgar as run

        return run(raw_path=raw_path, edition=get_current_context()["params"]["edgar_edition"])

    @task
    def stage_worldbank(raw_dir: str) -> str:
        from src.transform.worldbank import stage_worldbank as run

        return run(raw_dir=raw_dir)

    @task
    def stage_faostat(raw_path: str) -> str:
        from src.transform.faostat import stage_faostat as run

        return run(raw_path=raw_path)

    @task
    def validate_edgar(_staged: str) -> bool:
        from src.validation.rules import validate_edgar_staging

        return checks_passed(validate_edgar_staging)

    @task
    def validate_worldbank(_staged: str) -> bool:
        from src.validation.rules import validate_worldbank_staging

        return checks_passed(validate_worldbank_staging)

    @task
    def validate_faostat(_staged: str) -> bool:
        from src.validation.rules import validate_faostat_staging

        return checks_passed(validate_faostat_staging)

    @task
    def build_curated() -> dict:
        from src.transform.curated import build_curated as run

        return run()

    @task
    def build_faostat_curated(_paths: dict) -> dict:
        from src.transform.curated_faostat import build_faostat_curated as run

        return run()

    @task
    def validate_curated(_paths: dict) -> bool:
        from src.validation.rules import validate_curated, validate_faostat_curated

        return checks_passed(validate_curated) and checks_passed(validate_faostat_curated)

    @task
    def load_warehouse(_ok: bool) -> dict:
        from src.load.warehouse import load_warehouse as run

        return run()  # batch_id = time of the run, e.g. 20261001T031500Z

    @task
    def check_warehouse(_loaded: dict) -> bool:
        from src.load.warehouse import check_warehouse as run

        return checks_passed(run)

    @task
    def compare_formats(_ok: bool) -> str:
        from src.utils.file_formats import compare_formats as run

        return run()

    # Task order (>> means "runs before")
    edgar_ok = validate_edgar(stage_edgar(extract_edgar()))
    worldbank_ok = validate_worldbank(stage_worldbank(extract_worldbank()))
    faostat_ok = validate_faostat(stage_faostat(extract_faostat()))

    curated = build_curated()
    [edgar_ok, worldbank_ok] >> curated

    faostat_curated = build_faostat_curated(curated)   # needs dim_country and agri_country_year
    faostat_ok >> faostat_curated

    curated_ok = validate_curated(faostat_curated)
    check_warehouse(load_warehouse(curated_ok))
    compare_formats(curated_ok)


agri_emissions_pipeline()
