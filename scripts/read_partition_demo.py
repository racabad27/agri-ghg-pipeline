"""Partitioning demo: read ONE sector folder vs ALL sector folders of the EDGAR staging data.

Run (inside Docker):  docker compose exec airflow-scheduler python scripts/read_partition_demo.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so 'import src' works

import pandas as pd  # noqa: E402

from src.config import STAGING_DIR  # noqa: E402


def timed_read(**kwargs):
    start = time.perf_counter()
    df = pd.read_parquet(STAGING_DIR / "edgar", **kwargs)
    return df, (time.perf_counter() - start) * 1000


if __name__ == "__main__":
    folders = sorted(p.name for p in (STAGING_DIR / "edgar").iterdir() if p.is_dir())
    print(f"Partition folders ({len(folders)}): {folders}\n")

    everything, all_ms = timed_read()
    agriculture, one_ms = timed_read(filters=[("sector_key", "==", "agriculture")])

    print(f"All sectors : {len(everything):>8,} rows read in {all_ms:6.1f} ms")
    print(f"Agriculture : {len(agriculture):>8,} rows read in {one_ms:6.1f} ms "
          f"(only 1 of {len(folders)} folders opened)")
    print(f"\nThe filtered read touched {len(agriculture) / len(everything):.1%} of the rows.")
