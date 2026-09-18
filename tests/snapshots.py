"""Builds a snapshot from hand-made raw sources and loads it, the way the app does."""

from pathlib import Path

import duckdb

from common_cause.ingest.build import build_snapshot
from common_cause.ingest.snapshot import load_snapshot

from .raw_sources import RawSourceBuilder


def built_snapshot(sources: RawSourceBuilder, tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)
    snapshot_dir = tmp_path / "snapshot"
    build_snapshot(sources.write(raw_dir), snapshot_dir)
    return snapshot_dir


def loaded(sources: RawSourceBuilder, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    load_snapshot(con, built_snapshot(sources, tmp_path))
    return con
