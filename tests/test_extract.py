"""Tests for the extract step (no internet needed)."""
import zipfile

import openpyxl
import pytest

from src.extract import worldbank
from src.extract.edgar import check_edgar_workbook
from src.extract.faostat import check_faostat_zip, data_csv_name
from src.utils.errors import ExtractionError

SHEET = "GHG_by_sector_and_country"


def make_workbook(path, sheet=SHEET):
    workbook = openpyxl.Workbook()
    workbook.active.title = sheet
    workbook.active.append(["Substance", "Sector", "EDGAR Country Code", "Country", 1970])
    workbook.save(path)
    return path


def test_accepts_a_complete_workbook(tmp_path):
    check_edgar_workbook(make_workbook(tmp_path / "ok.xlsx"), SHEET)  # no error


def test_rejects_a_cut_off_download(tmp_path):
    good = make_workbook(tmp_path / "good.xlsx")
    cut_off = tmp_path / "cut_off.xlsx"
    cut_off.write_bytes(good.read_bytes()[:1000])  # like our first 142 KB download
    with pytest.raises(ExtractionError, match="not a valid .xlsx"):
        check_edgar_workbook(cut_off, SHEET)


def test_rejects_a_workbook_without_our_sheet(tmp_path):
    other = make_workbook(tmp_path / "other.xlsx", sheet="Something else")
    with pytest.raises(ExtractionError, match="not found"):
        check_edgar_workbook(other, SHEET)


def fake_page(page, pages, records):
    return [{"page": page, "pages": pages, "per_page": 2, "total": 3}, records]


def test_worldbank_reads_every_page(monkeypatch):
    pages = {1: fake_page(1, 2, [{"id": 1}, {"id": 2}]), 2: fake_page(2, 2, [{"id": 3}])}
    monkeypatch.setattr(worldbank, "get_json", lambda url, params: pages[params["page"]])
    payloads = worldbank.fetch_all_pages("SP.POP.TOTL")
    assert len(payloads) == 2
    assert sum(len(p[1]) for p in payloads) == 3


def test_worldbank_error_message_is_reported(monkeypatch):
    error = [{"message": [{"id": "120", "value": "Invalid value"}]}]
    monkeypatch.setattr(worldbank, "get_json", lambda url, params: error)
    with pytest.raises(ExtractionError, match="Unexpected World Bank response"):
        worldbank.fetch_all_pages("NOT.A.REAL.INDICATOR")


def make_faostat_zip(path, files):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return path


def test_faostat_finds_the_data_csv_next_to_code_lists(tmp_path):
    ok = make_faostat_zip(tmp_path / "ok.zip", {
        "Emissions_Totals_E_AreaCodes.csv": "Area Code,Area\n171,Philippines\n",
        "Emissions_Totals_E_All_Data_(Normalized).csv": "Area Code,Year,Value\n171,2023,1.5\n",
    })
    check_faostat_zip(ok)  # no error
    assert data_csv_name(ok) == "Emissions_Totals_E_All_Data_(Normalized).csv"


def test_faostat_rejects_a_cut_off_zip(tmp_path):
    good = make_faostat_zip(tmp_path / "good.zip", {"Emissions_Totals_E_All_Data.csv": "Area Code\n1\n" * 5000})
    cut_off = tmp_path / "cut_off.zip"
    cut_off.write_bytes(good.read_bytes()[:good.stat().st_size // 2])  # only the first half arrived
    with pytest.raises(ExtractionError, match="not a valid zip"):
        check_faostat_zip(cut_off)


def test_faostat_rejects_a_zip_without_data(tmp_path):
    only_codes = make_faostat_zip(tmp_path / "codes.zip", {"Emissions_Totals_E_Flags.csv": "Flag\nE\n"})
    with pytest.raises(ExtractionError, match="no data CSV"):
        check_faostat_zip(only_codes)
