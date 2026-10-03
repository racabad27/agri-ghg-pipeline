"""Extract: download the FAOSTAT "Emissions Totals" bulk file (a zip with a CSV) into the raw layer.

Raw file:  data/raw/faostat/pulled=<date>/Emissions_Totals_E_All_Data_(Normalized).zip
Metadata:  the same name + '.meta.json' (link, download time, size, SHA-256), written last.
A new download goes into a new dated folder, so older copies stay as history.
"""
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

from src.config import RAW_DIR, get_settings
from src.extract.http import download_file
from src.utils.errors import ExtractionError
from src.utils.files import utc_now, write_metadata
from src.utils.logger import get_logger

log = get_logger("extract.faostat")


def faostat_raw_path(pulled_on: date | None = None) -> Path:
    """Where today's copy goes. The file name is taken from the link."""
    pulled_on = pulled_on or date.today()
    file_name = get_settings()["faostat"]["url"].rsplit("/", 1)[-1]
    return RAW_DIR / "faostat" / f"pulled={pulled_on.isoformat()}" / file_name


def data_csv_name(zip_path: Path) -> str:
    """Name of the data CSV inside the zip. FAOSTAT zips can also hold small code lists
    (area codes, flags); the data file is the CSV with 'All_Data' in its name."""
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv") and "all_data" in n.lower()]
    if not names:
        raise ExtractionError(f"{Path(zip_path).name} has no data CSV (a file with 'All_Data' in its name)")
    return names[0]


def check_faostat_zip(path: Path) -> None:
    """Stop if the file is not a complete zip that contains the data CSV."""
    path = Path(path)
    if not path.exists():
        raise ExtractionError(f"File not found: {path}")
    if not zipfile.is_zipfile(path):
        raise ExtractionError(f"{path.name} is not a valid zip file (it may be cut off)")
    with zipfile.ZipFile(path) as archive:
        broken_part = archive.testzip()  # reads every file and checks its checksum
    if broken_part:
        raise ExtractionError(f"{path.name} is damaged (bad part inside: {broken_part})")
    data_csv_name(path)


def extract_faostat(force: bool = False) -> str:
    """Download today's copy of the FAOSTAT file unless we already have a good one.

    Returns the path of the raw file (as text, so Airflow can pass it to the next task).
    """
    url = get_settings()["faostat"]["url"]
    path = faostat_raw_path()
    meta_path = path.with_name(path.name + ".meta.json")

    if path.exists() and not force:
        try:
            check_faostat_zip(path)
            if not meta_path.exists():  # file was placed by hand: still record where it came from
                write_metadata(path, source="FAOSTAT Emissions Totals (FAO)", url=url,
                               retrieval_method="placed in raw folder manually", license="CC BY 4.0")
            log.info("FAOSTAT file already in the raw layer, skipping download: %s", path)
            return str(path)
        except ExtractionError as err:
            log.warning("Existing FAOSTAT file is not usable (%s). Downloading it again.", err)

    log.info("Saving today's FAOSTAT copy to %s", path)  # if the download fails, a copy saved here by hand works too
    download_file(url, path)
    try:
        check_faostat_zip(path)
    except ExtractionError:
        path.unlink(missing_ok=True)  # never leave a broken file in the raw layer
        raise
    write_metadata(path, source="FAOSTAT Emissions Totals (FAO)", url=url, retrieval_method="scripted download",
                   retrieved_at=utc_now(), license="CC BY 4.0")
    log.info("FAOSTAT file saved to %s", path)
    return str(path)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(extract_faostat())
