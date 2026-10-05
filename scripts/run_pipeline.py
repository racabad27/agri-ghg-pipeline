"""Run the whole pipeline (or one step) without Airflow. Useful for testing and debugging.

Examples (inside Docker):
  docker compose exec airflow-scheduler python scripts/run_pipeline.py
  docker compose exec airflow-scheduler python scripts/run_pipeline.py --step stage
  docker compose exec airflow-scheduler python scripts/run_pipeline.py --force-download
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so 'import src' works

from src.extract.edgar import extract_edgar  # noqa: E402
from src.extract.faostat import extract_faostat  # noqa: E402
from src.extract.worldbank import extract_worldbank  # noqa: E402
from src.load.warehouse import check_warehouse, load_warehouse  # noqa: E402
from src.transform.curated import build_curated  # noqa: E402
from src.transform.curated_faostat import build_faostat_curated  # noqa: E402
from src.transform.edgar import stage_edgar  # noqa: E402
from src.transform.faostat import stage_faostat  # noqa: E402
from src.transform.worldbank import stage_worldbank  # noqa: E402
from src.utils.file_formats import compare_formats  # noqa: E402
from src.utils.logger import get_logger, setup_logging  # noqa: E402
from src.validation.rules import (  # noqa: E402
    validate_curated, validate_edgar_staging, validate_faostat_curated, validate_faostat_staging,
    validate_worldbank_staging,
)

STEPS = ["extract", "stage", "validate_staging", "curate", "validate_curated", "load", "check_warehouse", "formats"]


def run(step: str, force_download: bool) -> None:
    if step == "extract":
        extract_edgar(force=force_download)
        extract_worldbank(force=force_download)
        extract_faostat(force=force_download)
    elif step == "stage":
        stage_edgar()
        stage_worldbank()
        stage_faostat()
    elif step == "validate_staging":
        validate_edgar_staging()
        validate_worldbank_staging()
        validate_faostat_staging()
    elif step == "curate":
        build_curated()
        build_faostat_curated()
    elif step == "validate_curated":
        validate_curated()
        validate_faostat_curated()
    elif step == "load":
        load_warehouse()
    elif step == "check_warehouse":
        check_warehouse()
    elif step == "formats":
        compare_formats()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the agricultural emissions pipeline without Airflow.")
    parser.add_argument("--step", choices=STEPS, help="run only this step (default: all steps in order)")
    parser.add_argument("--force-download", action="store_true", help="download sources again")
    args = parser.parse_args()

    setup_logging()
    log = get_logger("run_pipeline")
    for step in [args.step] if args.step else STEPS:
        log.info("===== step: %s =====", step)
        run(step, args.force_download)
    log.info("Done.")
