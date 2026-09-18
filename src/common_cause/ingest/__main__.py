"""`make ingest`: fetch the slice, build the Parquet snapshot, report what it holds."""

import argparse
import time
from pathlib import Path

import duckdb

from common_cause.ingest.build import build_snapshot
from common_cause.ingest.fetch import cached_sources, fetch_all
from common_cause.ingest.snapshot import DEFAULT_SNAPSHOT_DIR, load_snapshot

# Each committed file must stay under this size.
MAX_FILE_BYTES = 100 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m common_cause.ingest", description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"), help="download cache (not committed)")
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--skip-fetch", action="store_true", help="rebuild from the download cache only")
    args = parser.parse_args()

    print("Fetching sources")
    raw = cached_sources(args.raw_dir) if args.skip_fetch else fetch_all(args.raw_dir)

    print("Building snapshot")
    started = time.perf_counter()
    report = build_snapshot(raw, args.snapshot_dir)
    print(f"  built in {time.perf_counter() - started:.0f}s")

    started = time.perf_counter()
    load_snapshot(duckdb.connect(), args.snapshot_dir)
    print(f"  app-side load: {time.perf_counter() - started:.1f}s")

    print("\n| Table | Rows | File size | As-Of Date |")
    print("|---|---:|---:|---|")
    oversized = []
    for table, rows in report.table_rows.items():
        path = args.snapshot_dir / f"{table}.parquet"
        size = path.stat().st_size
        if size >= MAX_FILE_BYTES:
            oversized.append(path.name)
        as_of = duckdb.sql(f"select max(as_of_date) from read_parquet('{path}')").fetchall()[0][0]
        print(f"| `{table}` | {rows:,} | {size / 1e6:.1f} MB | {as_of} |")

    total = sum(report.relationship_types.values())
    print("\n| GLEIF relationship type (full file) | Records | Share |")
    print("|---|---:|---:|")
    for kind, records in report.relationship_types.items():
        print(f"| `{kind}` | {records:,} | {records / total:.1%} |")
    print(f"| total | {total:,} | |")
    if oversized:
        raise SystemExit(f"Snapshot files at or over {MAX_FILE_BYTES // 2**20} MiB: {', '.join(oversized)}")


if __name__ == "__main__":
    main()
