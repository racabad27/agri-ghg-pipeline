"""Compare CSV, JSON and Parquet on our main data product: file size, write/read time,
and whether column types survive a save-and-load round trip."""
from __future__ import annotations

import time

import pandas as pd

from src.config import CURATED_DIR, OUTPUTS_DIR
from src.utils.files import reset_dir
from src.utils.logger import get_logger

log = get_logger("formats")


def _timed(func) -> float:
    """Run func() and return how many seconds it took."""
    start = time.perf_counter()
    func()
    return time.perf_counter() - start


def compare_formats(table: str = "agri_country_year", repeats: int = 3) -> str:
    """Write the table in all three formats, read it back, and save a comparison report."""
    df = pd.read_parquet(CURATED_DIR / f"{table}.parquet")
    export_dir = reset_dir(CURATED_DIR / "exports")
    paths = {fmt: export_dir / f"{table}.{fmt}" for fmt in ["csv", "json", "parquet"]}

    writers = {
        "csv": lambda: df.to_csv(paths["csv"], index=False),
        "json": lambda: df.to_json(paths["json"], orient="records", lines=True),
        "parquet": lambda: df.to_parquet(paths["parquet"], index=False),
    }
    readers = {
        "csv": lambda: pd.read_csv(paths["csv"]),
        "json": lambda: pd.read_json(paths["json"], orient="records", lines=True),
        "parquet": lambda: pd.read_parquet(paths["parquet"]),
    }

    rows = []
    for fmt in ["csv", "json", "parquet"]:
        write_s = min(_timed(writers[fmt]) for _ in range(repeats))  # best of N runs
        read_s = min(_timed(readers[fmt]) for _ in range(repeats))
        back = readers[fmt]()
        changed = [c for c in df.columns if str(df[c].dtype) != str(back[c].dtype)]
        rows.append({
            "format": fmt,
            "size_kb": round(paths[fmt].stat().st_size / 1024, 1),
            "write_ms": round(write_s * 1000, 1),
            "read_ms": round(read_s * 1000, 1),
            "rows_read_back": len(back),
            "types_preserved": not changed,
            "columns_with_changed_type": ", ".join(changed) or "-",
        })

    report = pd.DataFrame(rows)
    out_dir = OUTPUTS_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(out_dir / "format_comparison.csv", index=False)
    with open(out_dir / "format_comparison.md", "w", encoding="utf-8") as f:
        f.write(f"# CSV vs JSON vs Parquet ({table}, {len(df):,} rows)\n\n")
        f.write(report.to_markdown(index=False) + "\n")  # to_markdown needs the 'tabulate' package
    log.info("Format comparison:\n%s", report.to_string(index=False))
    return str(out_dir / "format_comparison.csv")


if __name__ == "__main__":
    from src.utils.logger import setup_logging

    setup_logging()
    print(compare_formats())
