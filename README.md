# Common Cause

Finds Suppliers and Carriers in a procurement Portfolio that look independent but share a Common Cause: one Ultimate Parent, one physical address, or one jurisdiction. Built from public registries: GLEIF (who owns whom) and the FMCSA carrier census (who runs trucks). Vocabulary is defined in [`CONTEXT.md`](CONTEXT.md).

## Running it

Requires [uv](https://docs.astral.sh/uv/). A clean clone starts from the committed snapshot in `data/snapshot/`; nothing is downloaded.

```sh
make test       # run the test suite
make ingest     # re-fetch the slice from the live registries and rebuild data/snapshot/
make rebuild    # rebuild data/snapshot/ from the download cache in data/raw/ without fetching
```

`make ingest` downloads about 700 MB into `data/raw/` (not committed). Set `SODA_APP_TOKEN` to avoid throttling on the FMCSA API.

## The data snapshot

What the slice contains and why is set out in [`DECISIONS.md`](DECISIONS.md) entry 4. In short:

- **GLEIF Level 1**: LEI records with a US legal or headquarters address, plus both ends of every corporate consolidation edge worldwide.
- **GLEIF Level 2**: `IS_DIRECTLY_CONSOLIDATED_BY` and `IS_ULTIMATELY_CONSOLIDATED_BY` only. Fund and branch relationships are skipped.
- **GLEIF reporting exceptions** for those records, mapped to an Ownership Status (see [`ASSUMPTIONS.md`](ASSUMPTIONS.md) gap 2).
- **FMCSA census** (`az4n-8mr2`): Registrations with 10 or more power units, in any status, every published column.
- **FMCSA out-of-service orders** (`p2mt-9ige`) for those Registrations. The whole file is downloaded (about 400k rows) and narrowed to the census DOT numbers at build time, because a query listing 190k DOT numbers is not practical over SODA.

Source Records are kept as published: all values are text, exactly as the registry wrote them, including stale and lapsed records. Every table carries the As-Of Date of its source.

Row counts from the last `make ingest` (2026-09-18):

| Table | Rows | File size | As-Of Date |
|---|---:|---:|---|
| `gleif_record` | 541,003 | 54.2 MB | 2026-09-18 |
| `gleif_ownership_link` | 259,753 | 6.0 MB | 2026-09-18 |
| `gleif_reporting_exception` | 751,572 | 5.5 MB | 2026-09-18 |
| `gleif_ownership_status` | 541,003 | 5.4 MB | 2026-09-18 |
| `fmcsa_census` | 192,915 | 21.1 MB | 2026-09-14 |
| `fmcsa_oos_order` | 14,058 | 0.3 MB | 2026-09-18 |

`make ingest` also prints the full-file count per GLEIF relationship type, including the types the slice skips. On 2026-09-18: 259,753 of 488,309 records (53.2%) are consolidation edges, 226,597 (46.4%) fund structures and 1,959 (0.4%) international branches.

Building the snapshot from the download cache takes about 15 seconds. Loading it into DuckDB at app start takes under a second.

Five LEIs at the end of a consolidation edge do not appear in the Level 1 file, so their Ownership Links point at a company the snapshot cannot describe.
