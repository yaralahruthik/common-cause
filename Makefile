.PHONY: ingest rebuild resolve test typecheck lint

# Fetch the slice from the live registries and rebuild the committed snapshot in data/snapshot.
ingest:
	uv run python -m common_cause.ingest

# Rebuild the snapshot from the download cache in data/raw without fetching.
rebuild:
	uv run python -m common_cause.ingest --skip-fetch

# Resolve the snapshot into Entities; print match counts, scale signals and measured precision.
resolve:
	uv run python -m common_cause.resolve

test:
	uv run pytest

typecheck:
	uv run pyright

lint:
	uv run ruff check . && uv run ruff format --check .
