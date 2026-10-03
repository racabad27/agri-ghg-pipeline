"""Extract: download an indicator from the World Bank API (JSON) into the raw layer.

The API returns data in pages. We save the JSON of every page unchanged (only indented, so it is readable):
    data/raw/worldbank/<indicator>/pulled=<date>/page_001.json, page_002.json, ...
and write _manifest.json last. If _manifest.json exists, the pull is complete.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from src.config import RAW_DIR, get_settings
from src.extract.http import get_json
from src.utils.errors import ExtractionError
from src.utils.files import reset_dir, utc_now, write_json
from src.utils.logger import get_logger

log = get_logger("extract.worldbank")


def worldbank_raw_dir(indicator: str, pulled_on: date | None = None) -> Path:
    pulled_on = pulled_on or date.today()
    return RAW_DIR / "worldbank" / indicator / f"pulled={pulled_on.isoformat()}"


def fetch_all_pages(indicator: str) -> list:
    """Call the API page by page. Each page looks like [page_info, [records...]]."""
    settings = get_settings()["worldbank"]
    url = f"{settings['base_url']}/{indicator}"
    payloads, page, total_pages = [], 1, 1
    while page <= total_pages:
        payload = get_json(url, params={"format": "json", "per_page": settings["per_page"], "page": page})
        # On errors the API returns [{"message": [...]}] instead of [page_info, records]
        if not (isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], dict)
                and "pages" in payload[0]):
            raise ExtractionError(f"Unexpected World Bank response on page {page}: {str(payload)[:300]}")
        total_pages = int(payload[0]["pages"])
        payloads.append(payload)
        log.info("Page %d/%d: %d records", page, total_pages, len(payload[1] or []))
        page += 1

    expected = int(payloads[0][0]["total"])
    received = sum(len(p[1] or []) for p in payloads)
    if received != expected:
        raise ExtractionError(f"Expected {expected} records but received {received}")
    return payloads


def extract_worldbank(indicator: str | None = None, force: bool = False) -> str:
    """Download all pages of one indicator (default: population). Returns the folder path."""
    settings = get_settings()["worldbank"]
    indicator = indicator or settings["indicator"]
    folder = worldbank_raw_dir(indicator)
    manifest = folder / "_manifest.json"

    if manifest.exists() and not force:
        log.info("World Bank %s already pulled today, skipping: %s", indicator, folder)
        return str(folder)

    payloads = fetch_all_pages(indicator)
    reset_dir(folder)  # remove pages from an earlier, unfinished attempt
    for number, payload in enumerate(payloads, start=1):
        write_json(payload, folder / f"page_{number:03d}.json")
    write_json(
        {
            "source": "World Bank, World Development Indicators",
            "indicator": indicator,
            "url": f"{settings['base_url']}/{indicator}?format=json",
            "pages": len(payloads),
            "records": sum(len(p[1] or []) for p in payloads),
            "source_last_updated": payloads[0][0].get("lastupdated"),
            "retrieved_at": utc_now(),
            "retrieval_method": "scripted API calls",
            "license": "CC BY 4.0",
        },
        manifest,
    )
    log.info("World Bank %s saved to %s", indicator, folder)
    return str(folder)


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(extract_worldbank())
