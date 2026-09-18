.PHONY: ingest rebuild resolve serve test typecheck lint

# Fetch the slice from the live registries and rebuild the committed snapshot in data/snapshot.
ingest:
	uv run python -m common_cause.ingest

# Rebuild the snapshot from the download cache in data/raw without fetching.
rebuild:
	uv run python -m common_cause.ingest --skip-fetch

# Resolve the snapshot into Entities; print match counts, scale signals and measured precision.
resolve:
	uv run python -m common_cause.resolve

# Resolve the snapshot and serve the API on http://127.0.0.1:8000 (interactive docs at /docs).
serve:
	uv run python -m common_cause.api

test:
	uv run pytest

typecheck:
	uv run pyright

lint:
	uv run ruff check . && uv run ruff format --check .
