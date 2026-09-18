"""App-side access to the committed Parquet snapshot."""

from pathlib import Path

import duckdb

# Committed with the repository so a clean clone starts without downloading anything.
DEFAULT_SNAPSHOT_DIR = Path(__file__).resolve().parents[3] / "data" / "snapshot"


def load_snapshot(con: duckdb.DuckDBPyConnection, snapshot_dir: Path) -> None:
    """Materialises every snapshot file as a table named after it."""
    for path in sorted(snapshot_dir.glob("*.parquet")):
        con.execute(f"create or replace table {path.stem} as select * from read_parquet(?)", [str(path)])
