"""Downloads the slice from the live registries into a local cache directory.

Nothing here is tested offline; `make ingest` exercises it end to end. The cache makes reruns cheap:
a GLEIF file whose published size already matches on disk is not downloaded again.
"""

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from common_cause.ingest.build import MIN_POWER_UNITS, RawSources

GLEIF_PUBLISHES_URL = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes"
GLEIF_FILES = {"lei2": "gleif_level1.csv.zip", "rr": "gleif_relationships.csv.zip", "repex": "gleif_exceptions.csv.zip"}

SODA_BASE_URL = "https://data.transportation.gov"
FMCSA_CENSUS_DATASET = "az4n-8mr2"
FMCSA_OOS_DATASET = "p2mt-9ige"
SODA_PAGE_SIZE = 50_000

MANIFEST = "manifest.json"


def fetch_all(raw_dir: Path) -> RawSources:
    raw_dir.mkdir(parents=True, exist_ok=True)
    headers = {"X-App-Token": token} if (token := os.environ.get("SODA_APP_TOKEN")) else {}
    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(transport=transport, timeout=httpx.Timeout(60, read=300), headers=headers) as client:
        gleif_as_of, gleif_urls = _latest_gleif_publish(client)
        for kind, filename in GLEIF_FILES.items():
            url, size = gleif_urls[kind]
            _download(client, url, raw_dir / filename, expected_size=size)

        census_as_of = _soda_as_of(client, FMCSA_CENSUS_DATASET)
        _download_soda_csv(
            client,
            FMCSA_CENSUS_DATASET,
            raw_dir / "fmcsa_census.csv",
            where=f"power_units::number >= {MIN_POWER_UNITS}",
        )
        # The out-of-service file is small; it is narrowed to the census DOT numbers at build time.
        oos_as_of = _soda_as_of(client, FMCSA_OOS_DATASET)
        _download_soda_csv(client, FMCSA_OOS_DATASET, raw_dir / "fmcsa_oos.csv")

    manifest = {
        "gleif_as_of": gleif_as_of.isoformat(),
        "gleif_urls": {kind: url for kind, (url, _) in gleif_urls.items()},
        "fmcsa_census_as_of": census_as_of.isoformat(),
        "fmcsa_oos_as_of": oos_as_of.isoformat(),
    }
    (raw_dir / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    return cached_sources(raw_dir)


def cached_sources(raw_dir: Path) -> RawSources:
    """The sources a previous `fetch_all` left in `raw_dir`."""
    manifest = json.loads((raw_dir / MANIFEST).read_text())
    return RawSources(
        gleif_level1=raw_dir / GLEIF_FILES["lei2"],
        gleif_relationships=raw_dir / GLEIF_FILES["rr"],
        gleif_exceptions=raw_dir / GLEIF_FILES["repex"],
        gleif_as_of=date.fromisoformat(manifest["gleif_as_of"]),
        fmcsa_census=raw_dir / "fmcsa_census.csv",
        fmcsa_census_as_of=date.fromisoformat(manifest["fmcsa_census_as_of"]),
        fmcsa_oos=raw_dir / "fmcsa_oos.csv",
        fmcsa_oos_as_of=date.fromisoformat(manifest["fmcsa_oos_as_of"]),
    )


def _latest_gleif_publish(client: httpx.Client) -> tuple[date, dict[str, tuple[str, int]]]:
    """The As-Of Date of the newest Golden Copy and the full-file CSV url and size per file kind."""
    response = client.get(GLEIF_PUBLISHES_URL, params={"per_page": 1})
    response.raise_for_status()
    publish = response.json()["data"][0]
    files = {
        kind: (publish[kind]["full_file"]["csv"]["url"], int(publish[kind]["full_file"]["csv"]["size"]))
        for kind in GLEIF_FILES
    }
    return datetime.fromisoformat(publish["publish_date"]).date(), files


def _soda_as_of(client: httpx.Client, dataset: str) -> date:
    """The As-Of Date of a dataset: when the publisher last changed its rows."""
    response = client.get(f"{SODA_BASE_URL}/api/views/{dataset}.json")
    response.raise_for_status()
    return datetime.fromtimestamp(response.json()["rowsUpdatedAt"], tz=UTC).date()


def _download(client: httpx.Client, url: str, path: Path, expected_size: int) -> None:
    if path.exists() and path.stat().st_size == expected_size:
        print(f"  cached  {path.name}")
        return
    print(f"  fetch   {path.name} ({expected_size / 1e6:.0f} MB)")
    partial = path.with_suffix(path.suffix + ".part")
    with client.stream("GET", url) as response, partial.open("wb") as out:
        response.raise_for_status()
        for chunk in response.iter_bytes(1 << 20):
            out.write(chunk)
    partial.rename(path)


def _download_soda_csv(client: httpx.Client, dataset: str, path: Path, where: str | None = None) -> None:
    """Pages through a SODA dataset as CSV in a stable order, writing one header."""
    print(f"  fetch   {path.name}", end="", flush=True)
    partial = path.with_suffix(path.suffix + ".part")
    with partial.open("w", encoding="utf-8", newline="") as out:
        for offset in range(0, 10**9, SODA_PAGE_SIZE):
            params = {"$limit": SODA_PAGE_SIZE, "$offset": offset, "$order": ":id"}
            if where:
                params["$where"] = where
            response = client.get(f"{SODA_BASE_URL}/resource/{dataset}.csv", params=params)
            response.raise_for_status()
            header, _, body = response.text.partition("\n")
            if offset == 0:
                out.write(header + "\n")
            out.write(body)
            print(".", end="", flush=True)
            if not body.strip():
                break
    partial.rename(path)
    print(f" {path.stat().st_size / 1e6:.0f} MB")
