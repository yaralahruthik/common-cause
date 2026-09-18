# Common Cause

A procurement team diversifies by buying from several companies. Common Cause checks whether those companies really are several. Given a **Portfolio** of Supplier and Carrier names, it finds members that look independent but share a **Common Cause**: one Ultimate Parent, one physical address or one jurisdiction. Such a group is a **Hidden Concentration**. It is built from two public registries: GLEIF (who owns whom) and the FMCSA carrier census (who runs trucks). Vocabulary is defined in [`CONTEXT.md`](CONTEXT.md).

In the bundled sample of 15 food and beverage makers, three dairies that go by three names and run 2,966 trucks between them trace back to Prairie Farms Dairy, one by ownership and one by address. Hiland Dairy's GLEIF ownership chain ends at Prairie Farms Dairy. East Side Jersey Dairy files nothing with GLEIF, but its FMCSA Registration sits at Prairie Farms' own address. The sample is curated (see [The interface](#the-interface)).

- [`docs/architecture/`](docs/architecture/README.md): how data flows from source to storage, what the storage model is, and what happens when an analyst asks a question.
- [`docs/walkthrough.html`](docs/walkthrough.html): the whole project on one page. Download it and open it in a browser.
- [`DECISIONS.md`](DECISIONS.md), [`ASSUMPTIONS.md`](ASSUMPTIONS.md), [`AI_LOG.md`](AI_LOG.md): the decisions and what they cost, the gaps in the problem statement, and where the coding agent was wrong.

## Running it from a clean clone

Needs `make`, [uv](https://docs.astral.sh/uv/) (it fetches Python 3.13 itself if missing) and Node.js 22.12 or later. Nothing is downloaded from the registries: a clean clone starts from the committed snapshot in `data/snapshot/`.

```sh
git clone https://github.com/yaralahruthik/common-cause.git
cd common-cause
make web        # install and build the interface
make serve      # load and resolve the snapshot, then serve everything on http://127.0.0.1:8000
```

Open http://127.0.0.1:8000 and choose the sample, or paste your own names. `make serve` takes about 10 seconds to start, 8 of them spent resolving the whole snapshot, which it does on every start-up.

Other targets:

```sh
make test       # run the Python test suite
make web-test   # typecheck and test the interface
make resolve    # resolve the snapshot and print the numbers in "Entity resolution" below
make ingest     # re-fetch the slice from the live registries and rebuild data/snapshot/
make rebuild    # rebuild data/snapshot/ from the download cache in data/raw/ without fetching
make web-dev    # serve the interface with live reload on http://127.0.0.1:5173, beside `make serve`
```

`make ingest` downloads about 700 MB into `data/raw/` (not committed). Set `SODA_APP_TOKEN` to avoid throttling on the FMCSA API.

**Checked:** on 2026-09-18, a fresh clone from GitHub on macOS (Apple silicon, uv 0.11, Node 24) passed all 154 Python and 33 interface tests, built the interface and served the sample. It has not been run on Linux or Windows.

## What works

- **Ingest.** `make ingest` fetches the latest GLEIF Golden Copy and both FMCSA datasets and rebuilds the snapshot (about 15 seconds from the download cache). Every row keeps its As-Of Date.
- **Entity resolution.** All 733,918 Source Records resolve into Entities in about 7 seconds, in SQL inside DuckDB. Every Match carries its evidence, and Possible Matches never merge records.
- **Ownership.** Every GLEIF record gets an Ultimate Parent by walking its chain, with cycles, broken chains and disagreements with the Declared Ultimate Parent handled and counted. Every Entity has a three-state Ownership Status. A missing parent is never read as independence.
- **Hidden Concentrations.** A pasted or uploaded Portfolio is matched, the analyst confirms or rejects the uncertain names, and the result is ranked. Concentrations that rest on an unconfirmed Match are marked tentative, and the unverifiable share is always stated.
- **The interface.** Three screens take an analyst from a list of names to one Concentration's ownership path, Registrations and out-of-service orders. Verdicts survive a restart and a rebuild.

## What does not work

- **There are no Supply Links, so there are no Tiers.** Nothing in these sources says who supplies whom. The tool answers "which of my suppliers share an owner or a site", not "who supplies my suppliers" ([`ASSUMPTIONS.md`](ASSUMPTIONS.md) gap 1).
- **The join between the registries is thin.** 2.1% of Registrations have a Firm Match to a GLEIF record. Most companies that run trucks have no LEI. In a random Portfolio of 15 private-fleet operators, 14 names matched a Registration and ownership was unverifiable for all 14.
- **The Possible band is weak in Pass B.** Corroborated Possible Matches between FMCSA and GLEIF were right 5 times in 15 (33%), mostly because they find a parent and its subsidiary at one address.
- **The precision figures were not independently checked.** The 102 labels were made by an AI assistant, and 17 pairs per band is a small sample (see [Measured precision](#measured-precision)).
- **Concentrations that share a member are not joined.** The three dairies above show up as two Concentrations, a shared parent and a shared address. The analyst has to put the two together.
- **A real industrial park is discounted.** An address shared by more than 10 distinct names is treated as an Agent Address, so fifteen tenants of one park do not form a Concentration.
- **The slice under-samples small carriers.** It keeps Registrations with 10 or more power units: 192,915 of the census's 4,502,467 rows (4.3%). Two blocking keys over 1,000 records (names starting `CAPITAL ` in New York and in California) are skipped, so records in them are never matched.
- **Freshness is manual.** Delta ingest is designed, not built. The snapshot is only as current as the last `make ingest`.
- **Single user, no access control.** Anyone who can reach the server can read or change any Portfolio by its id. One connection does all the writes.
- **Scale is argued, not tested.** [`DECISIONS.md`](DECISIONS.md) entry 4 names what breaks first at fifty times the volume. Nothing was run at that size.
- **Cut:** LLM adjudication of the Possible band ([`DECISIONS.md`](DECISIONS.md) entry 8).

## Time spent

About 7 hours, from the first plan to this README.


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

## Hidden Concentrations

`common_cause.exposure` finds the Hidden Concentrations in a Portfolio, and `make serve` puts it behind an HTTP API. At start-up the API loads the snapshot, resolves it and walks every ownership chain, which takes about 8 seconds. After that, matching a 25-name Portfolio takes about 40 ms and its exposure about 60 ms.

| Endpoint | What it does |
|---|---|
| `POST /portfolios` | Takes `{"members": [{"name", "state"?, "city"?}], "sample"?}`, stores the Portfolio and returns each member with its Matches. |
| `GET /portfolios/{id}` | The members, their Matches, and any Verdicts. |
| `PUT /portfolios/{id}/members/{member_id}` | Changes the name, state or city a member is searched by, and returns it matched again. |
| `PUT /portfolios/{id}/members/{member_id}/verdicts/{entity_id}` | Takes `{"verdict": "confirmed" \| "rejected"}` on one of that member's Matches. |
| `DELETE /portfolios/{id}/members/{member_id}/verdicts/{entity_id}` | Withdraws that Verdict. |
| `GET /portfolios/{id}/exposure` | Hidden Concentrations ranked by share of the Portfolio (shared jurisdictions last), each with a stable `id`; how many members are firmly in one (`affected`) and how many would be if every Possible Match held; Ownership Status per member, walked/declared disagreements, and the As-Of Date of each source. |
| `GET /portfolios/{id}/concentrations/{concentration_id}` | One Concentration for the detail screen: each member's Match (and, if it is not firm, the alternatives), ownership path with every hop's jurisdiction, Registrations with status, power units, address, last MCS-150 filing and out-of-service orders, and the shared site with everyone else registered there. |
| `GET /sample` | The sample Portfolio, and what a random Portfolio of the same size finds. |

`affected` counts a member only when its own Match is firm and it sits in a firm Concentration other than a shared jurisdiction. A member firmly matched into a Concentration that is tentative because of someone else's Possible Match is not counted.

**Matching a Portfolio name.** The name is normalised the same way Source Records are. If exactly one Entity goes by that normalised name (within the state and city, when given), it is a Firm Match. The member also gets up to 3 Possible Matches: the other Entities whose names score at least 0.8, exact hits held by several Entities included. They stay beside a Firm Match, so an analyst who rejects it still has the near names to confirm. Many names hit twice, once as the FMCSA Registration and once as the GLEIF record that resolution did not firmly join. The state or city then picks one, and the analyst's Verdict settles the rest.

**Ultimate Parent.** Direct Ownership Links are walked upward by a recursive CTE, which stops on a cycle or after 20 hops. Where the chain breaks, the Declared Ultimate Parent stands in. Where nothing is declared, the furthest company reached stands in; inside a cycle that is the smallest LEI on it, so every company in the cycle gets the same one. A complete walk that ends somewhere other than the Declared Ultimate Parent is kept, and the disagreement is reported. On the 2026-09-18 snapshot:

| Ultimate Parent found by | Chain break | GLEIF records | Disagreements |
|---|---|---:|---:|
| walking direct links | | 524,712 | 2,436 |
| the Declared Ultimate Parent | missing direct link | 16,287 | |
| the Declared Ultimate Parent | cycle | 1 | |
| the furthest company reached | cycle | 3 | |

13,606 of the missing direct links are companies that file an ultimate parent and no direct one. The rest are chains whose top company declares an ultimate parent but has no direct link to it. No chain is longer than 9 hops.

**Common Causes.** Three things can be shared:

- the Ultimate Parent of any of the Entity's LEIs
- a GLEIF headquarters or FMCSA physical address that is not an Agent Address
- a GLEIF legal jurisdiction

A Carrier with no GLEIF record can only share an address, because FMCSA publishes no ownership. Two members that resolve to one Entity are one company under two names, so they never form a Concentration on their own.

A Concentration is **tentative** unless at least two different Entities reach it through Firm or confirmed Matches. Its share counts only the firmly matched members. The share it would have if every Possible Match held is reported beside it. A rejected Match drops out. When a member has a Firm or confirmed Match, its other Matches drop out too.

Shared jurisdictions are listed after every other Concentration, however large. Most US companies are incorporated in a few states, so a shared jurisdiction is nearly always the largest Concentration and the least telling. In a 25-name food-and-beverage test Portfolio, 52% of it shared Delaware.

**Ownership Status** is read from the member's firmly matched Entity. An Entity that holds no GLEIF record has an Undisclosed Parent. A member with no Firm or confirmed Match has no Ownership Status yet, because it is not yet known which company it is. The exposure reports those members separately, so it can say "ownership unverifiable: N of M matched, K not yet matched".

**Verdicts** hold for their own Portfolio only. Each one is stored against the Source Record the Match was made through, an LEI or a USDOT number. Entity ids are recomputed whenever the snapshot is resolved, so a Verdict keyed to one could quietly stop applying after a rebuild. Portfolios and Verdicts are stored in `data/workspace.duckdb`, which is not committed. It is attached to the one connection the API reads the graph through, and a lock makes that connection the only writer.

## The interface

`web/` is a React and TypeScript app with three screens in a fixed order: Portfolio, Exposure and Concentration detail (`DECISIONS.md` entry 7). `make web` builds it and `make serve` serves it beside the API.

- **Portfolio**: paste names or upload a CSV, or open the sample. Names are grouped into Needs your decision (Possible Matches, each with its evidence), Not found (edit the name and search again) and Matched (with evidence and Ownership Status). Rejecting a match moves the name to Not found, with Undo.
- **Exposure**: one sentence for the CPO, three figures, the Hidden Concentrations ranked by share, and shared jurisdictions and unverifiable ownership in their own sections. A Concentration that rests on an undecided name is dashed and marked tentative.
- **Concentration detail**: the ownership tree from each member up to the shared parent, or both members pointing at the shared address; each member's Registrations and out-of-service orders; the As-Of Date of each source. A tentative Concentration asks for the missing Verdict in place.

**The sample is curated.** The 15 food and beverage makers in `src/common_cause/sample.py` were chosen because their records are in the snapshot, so they find what they were chosen to find: 4 Hidden Concentrations plus 1 tentative, affecting 7 of 15. The interface sets beside it a list of 15 companies drawn at random from active FMCSA Registrations that run a private fleet. That list finds none.


