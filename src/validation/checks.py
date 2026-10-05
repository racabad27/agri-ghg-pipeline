"""Reusable data-quality checks.

Every check returns a CheckResult. run_checks() logs every result, saves a JSON report in
outputs/validation/, and raises DataQualityError if an 'error' check failed. In Airflow that
makes the task fail (red), so a data problem is visible instead of silently loaded.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from src.config import OUTPUTS_DIR
from src.utils.errors import DataQualityError
from src.utils.files import utc_now, write_json
from src.utils.logger import get_logger

log = get_logger("validation")


@dataclass
class CheckResult:
    check: str           # what we tested
    passed: bool         # did it pass?
    details: str         # numbers that explain the result
    severity: str = "error"  # "error" stops the pipeline, "warning" is only logged


def expect_columns(df: pd.DataFrame, columns: list[str]) -> CheckResult:
    """Schema check: all required columns exist."""
    missing = [c for c in columns if c not in df.columns]
    return CheckResult("schema: required columns present", not missing,
                       f"missing: {missing}" if missing else f"all {len(columns)} columns present")


def expect_not_null(df: pd.DataFrame, columns: list[str]) -> CheckResult:
    """Nullability check: these columns must never be empty."""
    nulls = {c: int(df[c].isna().sum()) for c in columns}
    bad = {c: n for c, n in nulls.items() if n}
    return CheckResult(f"not null: {', '.join(columns)}", not bad,
                       f"null counts: {bad}" if bad else "no nulls")


def expect_unique(df: pd.DataFrame, key: list[str]) -> CheckResult:
    """Uniqueness check: one row per key (no duplicates)."""
    duplicates = int(df.duplicated(subset=key).sum())
    return CheckResult(f"unique key: ({', '.join(key)})", duplicates == 0, f"{duplicates} duplicate rows")


def expect_values_in(df: pd.DataFrame, column: str, allowed: list) -> CheckResult:
    """Accepted-values check: a column only contains values from a known list."""
    unexpected = sorted(set(df[column].dropna().unique()) - set(allowed), key=str)
    return CheckResult(f"accepted values: {column}", not unexpected,
                       f"unexpected: {unexpected[:10]}" if unexpected else f"{df[column].nunique()} known values")


def expect_between(df: pd.DataFrame, column: str, min_value=None, max_value=None,
                   severity: str = "error") -> CheckResult:
    """Range check: values stay inside [min_value, max_value]."""
    values = df[column].dropna()
    too_low = int((values < min_value).sum()) if min_value is not None else 0
    too_high = int((values > max_value).sum()) if max_value is not None else 0
    return CheckResult(f"range: {column} in [{min_value}, {max_value}]", too_low + too_high == 0,
                       f"{too_low} below, {too_high} above (min={values.min()}, max={values.max()})",
                       severity)


def expect_row_count_at_least(df: pd.DataFrame, minimum: int) -> CheckResult:
    """Row-count check: catches a half-empty file or a filter that removed too much."""
    return CheckResult(f"row count >= {minimum:,}", len(df) >= minimum, f"{len(df):,} rows")


def expect_true(check: str, condition: bool, details: str, severity: str = "error") -> CheckResult:
    """For business rules that need custom logic (e.g. totals that must add up)."""
    return CheckResult(check, bool(condition), details, severity)


def run_checks(dataset: str, results: list[CheckResult]) -> dict:
    """Log and save all results; raise DataQualityError if any 'error' check failed."""
    failed = [r for r in results if not r.passed and r.severity == "error"]
    for r in results:
        status = "PASS" if r.passed else ("FAIL" if r.severity == "error" else "WARN")
        log.log(20 if r.passed else 30, "[%s] %s | %s: %s", dataset, status, r.check, r.details)

    report = {
        "dataset": dataset,
        "checked_at": utc_now(),
        "passed": not failed,
        "checks_run": len(results),
        "checks_failed": len(failed),
        "results": [asdict(r) for r in results],
    }
    path = write_json(report, OUTPUTS_DIR / "validation" / f"{dataset}.json")
    log.info("[%s] %d/%d checks passed. Report: %s", dataset, len(results) - len(failed), len(results), path)

    if failed:
        summary = "; ".join(f"{r.check} ({r.details})" for r in failed)
        raise DataQualityError(f"{dataset}: {len(failed)} check(s) failed: {summary}")
    return report
