"""Tests for the reusable data-quality checks."""
import pandas as pd
import pytest

from src.utils.errors import DataQualityError
from src.validation.checks import (
    expect_between, expect_columns, expect_not_null, expect_row_count_at_least,
    expect_true, expect_unique, expect_values_in, run_checks,
)

DF = pd.DataFrame({"code": ["PHL", "IND", "IND"], "year": [2024, 2024, 2025], "value": [1.5, None, -2.0]})


@pytest.fixture(autouse=True)
def reports_in_temp_folder(tmp_path, monkeypatch):
    """Save the reports these tests create in a temporary folder, not in the project's outputs/."""
    monkeypatch.setattr("src.validation.checks.OUTPUTS_DIR", tmp_path)


def test_columns():
    assert expect_columns(DF, ["code", "year"]).passed
    assert not expect_columns(DF, ["code", "missing_column"]).passed


def test_not_null():
    assert expect_not_null(DF, ["code"]).passed
    assert not expect_not_null(DF, ["value"]).passed


def test_unique():
    assert expect_unique(DF, ["code", "year"]).passed
    assert not expect_unique(DF, ["code"]).passed


def test_values_in():
    assert expect_values_in(DF, "code", ["PHL", "IND"]).passed
    assert not expect_values_in(DF, "code", ["PHL"]).passed


def test_between():
    assert not expect_between(DF, "value", min_value=0).passed   # -2.0 is below 0
    assert expect_between(DF, "year", 2000, 2030).passed


def test_row_count():
    assert expect_row_count_at_least(DF, 3).passed
    assert not expect_row_count_at_least(DF, 4).passed


def test_run_checks_raises_on_error():
    with pytest.raises(DataQualityError, match="1 check"):
        run_checks("unit_test", [expect_true("always passes", True, ""), expect_true("always fails", False, "")])


def test_warnings_do_not_stop_the_pipeline():
    report = run_checks("unit_test_warning", [expect_true("soft rule", False, "", severity="warning")])
    assert report["passed"]
