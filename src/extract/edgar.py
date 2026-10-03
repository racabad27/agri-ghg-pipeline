"""Extract: download the EDGAR greenhouse-gas workbook (Excel) into the raw layer.

Raw file:  data/raw/edgar/edition=<year>/EDGAR_<year>_GHG_booklet_<year>.xlsx
Metadata:  the same name + '.meta.json' (link, download time, size, SHA-256)
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import openpyxl

from src.config import RAW_DIR, get_settings
from src.extract.http import download_file
from src.utils.errors import ExtractionError
from src.utils.files import utc_now, write_metadata
from src.utils.logger import get_logger

log = get_logger("extract.edgar")


def edgar_url(edition: int) -> str:
    return get_settings()["edgar"]["url_template"].format(edition=edition)


def edgar_raw_path(edition: int) -> Path:
    return RAW_DIR / "edgar" / f"edition={edition}" / f"EDGAR_{edition}_GHG_booklet_{edition}.xlsx"


def check_edgar_workbook(path: Path, sheet: str) -> None:
    """Stop if the file is not a complete Excel workbook with the sheet we need.

    Our first manual download was cut off at 142 KB and could not be opened.
    An .xlsx file is a zip archive, so a cut-off file fails the zip test below.
    """
    path = Path(path)
    if not path.exists():
        raise ExtractionError(f"File not found: {path}")
    if not zipfile.is_zipfile(path):
        raise ExtractionError(f"{path.name} is not a valid .xlsx file (it may be cut off)")
    with zipfile.ZipFile(path) as archive:
        broken_part = archive.testzip()
    if broken_part:
        raise ExtractionError(f"{path.name} is damaged (bad part inside: {broken_part})")
    workbook = openpyxl.load_workbook(path, read_only=True)
    try:
        sheets = workbook.sheetnames
    finally:
        workbook.close()
    if sheet not in sheets:
        raise ExtractionError(f"Sheet '{sheet}' not found in {path.name}. Sheets: {sheets}")


def extract_edgar(edition: int | None = None, force: bool = False) -> str:
    """Download the EDGAR workbook unless we already have a good copy.

    Returns the path of the raw file (as text, so Airflow can pass it to the next task).
    """
    settings = get_settings()["edgar"]
    edition = int(edition or settings["edition"])
    url = edgar_url(edition)
    path = edgar_raw_path(edition)
    meta_path = path.with_name(path.name + ".meta.json")

    if path.exists() and not force:
        try:
            check_edgar_workbook(path, settings["sheet"])
            if not meta_path.exists():  # file was placed by hand: still record where it came from
                write_metadata(path, source="EDGAR (European Commission, JRC)", url=url,
                               edition=edition, retrieval_method="placed in raw folder manually")
            log.info("EDGAR %s already in the raw layer, skipping download: %s", edition, path)
            return str(path)
        except ExtractionError as err:
            log.warning("Existing EDGAR file is not usable (%s). Downloading it again.", err)

    download_file(url, path)
    try:
        check_edgar_workbook(path, settings["sheet"])
    except ExtractionError:
        path.unlink(missing_ok=True)  # never leave a broken file in the raw layer
        raise
    write_metadata(path, source="EDGAR (European Commission, JRC)", url=url,
                   edition=edition, retrieval_method="scripted download", retrieved_at=utc_now())
    log.info("EDGAR %s saved to %s", edition, path)
    return str(path)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(extract_edgar())
