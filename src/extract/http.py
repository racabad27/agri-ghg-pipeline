"""HTTP helpers with retries, so slow websites do not break the pipeline."""
from __future__ import annotations

import time
from pathlib import Path

import requests

from src.config import get_settings
from src.utils.errors import ExtractionError
from src.utils.logger import get_logger

log = get_logger("extract.http")


def _should_retry(error: Exception) -> bool:
    """Retry network problems and server errors, but not '404 Not Found'-type errors."""
    if isinstance(error, requests.HTTPError) and error.response is not None:
        status = error.response.status_code
        return status >= 500 or status == 429  # 429 = too many requests
    return True  # timeouts, connection resets, incomplete files ...


def _request(url: str, params: dict | None = None, stream: bool = False) -> requests.Response:
    """GET a URL with retries. Raises ExtractionError when all attempts fail."""
    settings = get_settings()["http"]
    attempts = settings["retries"]
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                url,
                params=params,
                stream=stream,
                timeout=settings["timeout_seconds"],
                headers={"User-Agent": settings["user_agent"]},
            )
            response.raise_for_status()
            return response
        except requests.RequestException as err:
            log.warning("Request failed (attempt %d/%d): %s", attempt, attempts, err)
            if attempt == attempts or not _should_retry(err):
                raise ExtractionError(f"Could not get {url}: {err}") from err
            time.sleep(settings["backoff_seconds"] * attempt)
    raise ExtractionError(f"Could not get {url}")  # not reached, keeps linters happy


def download_file(url: str, destination: Path) -> Path:
    """Download a file. It is written to '<name>.part' first and renamed at the end,
    so a failed download never leaves a half-written file with the real name."""
    destination = Path(destination)
    temp_path = destination.with_name(destination.name + ".part")

    log.info("Downloading %s", url)
    response = _request(url, stream=True)
    destination.parent.mkdir(parents=True, exist_ok=True)  # only after the server answered
    try:
        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    except requests.RequestException as err:
        temp_path.unlink(missing_ok=True)
        raise ExtractionError(f"Download of {url} was interrupted: {err}") from err
    finally:
        response.close()

    # If the server told us the size, make sure we got all of it.
    expected = response.headers.get("Content-Length")
    actual = temp_path.stat().st_size
    if expected and not response.headers.get("Content-Encoding") and int(expected) != actual:
        temp_path.unlink(missing_ok=True)
        raise ExtractionError(f"Incomplete download: got {actual} of {expected} bytes")

    temp_path.replace(destination)
    log.info("Saved %s (%.2f MB)", destination, actual / 1_000_000)
    return destination


def get_json(url: str, params: dict | None = None):
    """GET a URL and return the parsed JSON body."""
    response = _request(url, params=params)
    try:
        return response.json()
    except ValueError as err:
        raise ExtractionError(f"{url} did not return valid JSON: {response.text[:200]}") from err
