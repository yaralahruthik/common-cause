# Common Cause

Finds Suppliers and Carriers in a procurement Portfolio that look independent but share a Common Cause: one Ultimate Parent, one physical address, or one jurisdiction. Built from public registries: GLEIF (who owns whom) and the FMCSA carrier census (who runs trucks). Vocabulary is defined in [`CONTEXT.md`](CONTEXT.md).

## Running it

Requires [uv](https://docs.astral.sh/uv/). A clean clone starts from the committed snapshot in `data/snapshot/`; nothing is downloaded.

```sh
make test       # run the test suite
make ingest     # re-fetch the slice from the live registries and rebuild data/snapshot/
make rebuild    # rebuild data/snapshot/ from the download cache in data/raw/ without fetching
make resolve    # resolve the snapshot into Entities and print the numbers in "Entity resolution" below
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

## Entity resolution

`common_cause.resolve` turns Source Records into Entities, in SQL inside DuckDB, using core functions only. The rules and why they were chosen are in [`DECISIONS.md`](DECISIONS.md) entry 3. It runs in about 7 seconds over the whole snapshot and writes these tables:

- `match`: every Firm and Possible Match. Each row has the signals behind it and one line of evidence written for an analyst, such as `names "SCOTLAND OIL COMPANY INC" / "SCOTLAND OIL CO., INC." similarity 1.00; same address 114 GRANT AVE 48801-2219`.
- `entity_member`: every Source Record and the Entity it belongs to. Entities are connected components over Firm Matches only.
- `entity`: one row per Entity, with its size. Two flags mark Entities not to trust: `oversized` (more than 25 records) and `several_leis` (holds two LEIs, which are two legal entities, so a wrong Firm Match bridged them).
- `agent_address`: 4,400 addresses shared by more than 10 distinct names, such as `251 LITTLE FALLS DR 19808` (4,505 names).

**Pass A** matches Registrations within FMCSA to one Carrier. **Pass B** matches Registrations to GLEIF records. GLEIF records are not matched to each other, because an LEI already identifies one legal entity.

### What it found (2026-09-18 snapshot)

| Pass | Band | Matches |
|---|---|---:|
| A | Firm | 5,870 |
| A | Possible, corroborated | 1,560 |
| B | Firm | 4,065 |
| B | Possible, corroborated | 680 |
| B | Possible, name only | 6,681 |

A pair is *corroborated* when it shares a ZIP (outside an Agent Address), a phone, an officer, or a prior-revoked-number pointer. *Name only* means it shares none of these.

**Cross-source match rate.** 4,065 of 192,915 Registrations (2.1%) have a Firm Match to a GLEIF record. Another 5,964 (3.1%) have only a Possible one. 3,859 of 187,392 Carrier Entities (2.1%) include a GLEIF record. Most carriers are private companies with no LEI, so the join between the two registries is thin. [`ASSUMPTIONS.md`](ASSUMPTIONS.md) gap 5 anticipated this.

### Measured precision

102 Matches were sampled, 17 from each pass and band, with a fixed seed. Each was labelled from the published records (by an AI assistant; see below), and the labels are committed in [`data/labels/match_labels.csv`](data/labels/match_labels.csv). `make resolve` re-measures them against the rules as they stand.

| Pass | Band | Same Entity | Different | Unsure | Precision |
|---|---|---:|---:|---:|---:|
| A | Firm | 17 | 0 | 0 | 100% |
| A | Possible, corroborated | 15 | 0 | 2 | 100% |
| A | Possible, name only (no longer kept) | 0 | 15 | 2 | 0% |
| B | Firm | 16 | 0 | 1 | 100% |
| B | Possible, corroborated | 5 | 10 | 2 | 33% |
| B | Possible, name only | 9 | 7 | 1 | 56% |

How to read this:

- **The labeller.** The labels were made by an AI assistant (Claude), reading the two records, their addresses and the evidence line and applying general knowledge of the companies. No domain expert labelled them, and nobody checked the labels against a third source. Every label carries a note giving its reason.
- **What "same" means.** In Pass A, the two Registrations belong to one operating business, even when that business uses two legal names at one address and phone. In Pass B, the Registration is held by that GLEIF legal entity. A parent, subsidiary or sister company counts as different.
- **Sample size.** 17 per band is small. 17 of 17 correct is consistent with a true precision as low as about 82%.
- **Rules changed after looking.** The rules changed twice after seeing data. A first 102-pair sample, never labelled, showed franchise trade names, non-Latin names and prefix-sharing words producing false matches; those rules were fixed and a fresh sample was drawn with a new seed. After this sample was labelled, Pass A name-only pairs (0 of 15 correct) were dropped from the Possible band. Their row above shows the measurement that caused the change.
- **Where the Possible band is weak.** In Pass B, "corroborated" mostly finds a parent and a subsidiary at one address or in one ZIP (Kimball International and Kimball International Brands). Those are exactly the pairs an analyst should see, but they are not the same Entity.

### Scale signals

These are the early warnings named in [`DECISIONS.md`](DECISIONS.md) entry 4.

| Records per blocking key | Keys |
|---|---:|
| 1 | 2,172,326 |
| 2 | 178,163 |
| 3-5 | 83,094 |
| 6-10 | 21,637 |
| 11-25 | 7,005 |
| 26-100 | 2,141 |
| 101-1000 | 297 |
| >1000 | 2 |

Two blocks exceed the 1,000-record cap and are skipped: names starting `CAPITAL ` in New York (1,743) and in California (1,039). Candidate pairs total about 3.4 million.

| Source Records per Entity | Entities |
|---|---:|
| 1 | 715,716 |
| 2 | 8,321 |
| 3-5 | 492 |
| 6-10 | 3 |
| 11-25 | 2 |
| over 25 | 0 |

No Entity exceeds 25 records. Two hold more than one LEI and are flagged.

