# Decision log

Each entry: what I chose, what I chose against and why not, what it cost, what would change my mind. Terms in **bold** are defined in `CONTEXT.md`.

## 1. Outcome: Tier 2/3 Supplier Intelligence, reframed as Hidden Concentration discovery

**Chose.** Given a **Portfolio**, find members that look independent but share a **Common Cause**. See `ASSUMPTIONS.md` gap 1 for why it is not literally "Tier 2/3".

**Against.** *Geographic Supplier Risk*: a map is the deliverable, and geocoding ~100k messy addresses would eat the budget. *Supplier Risk Intelligence*: continuous scoring needs a time series; from one snapshot, a score is an invented weighted sum I could not defend past the first "why".

**Cost.** No map, so the motivating example (a flood closes an industrial park) is not served. No single per-supplier number for the CPO.

**Would change my mind.** Historical snapshots of the FMCSA census (then degradation-over-time becomes real and scoring becomes defensible).

## 2. Storage: DuckDB with recursive CTEs

See `docs/adr/0001-duckdb-as-the-graph-store.md`.

**Chose.** One DuckDB file. Traversal by recursive CTE with a cycle guard and depth cap.

**Against.** *Neo4j*: one traversable edge type and shallow chains, so Cypher buys little and costs a server in the clean-clone path. *Postgres*: nothing is transactional except **Verdicts**.

**Cost.** Single writer. No graph query language, so every new traversal is hand-written SQL. DuckPGQ (SQL/PGQ) could not be relied on: the community extension failed to download for the current DuckDB version when tested.

**Would change my mind.** Real **Supply Links** arriving (variable-length paths over several edge types favours a graph database), or multi-user writes and daily delta upserts (favours Postgres).

## 3. Resolution: hand-written rules in SQL, three bands, non-destructive

**Chose.** **Source Records** stay immutable. Names are normalised (legal forms stripped, accents stripped, tokens sorted), candidate pairs come from blocking, and scoring uses DuckDB core functions only. A **Firm Match** needs a strong name score *and* one independent corroborating signal (ZIP, phone, officer, or an explicit prior-revoked-number pointer). Weaker pairs become **Possible Matches**, shown to the analyst and never used to form **Entities**. Entities are connected components over Firm Matches, with a cluster-size guard.

Refined after reading real pairs (measured precision is in the README):

- **Name score.** Each word is scored against its closest word in the other name with `jaro_winkler_similarity`, and a word scoring below 0.9 counts as different. Jaro-Winkler over the whole sorted string let shared leading words carry unrelated names, scoring `CONSTRUCTION INDUSTRIAL PRECISE` against `... STEEL` at 0.95.
- **Crowded values are not evidence.** A phone or officer shared by more than 10 distinct names is treated like an **Agent Address**.
- **Brands are not identities.** A trade name carried by more than two different legal names (a franchise, or a group's brand) is not used to match.
- **Name alone is not enough inside FMCSA.** Two Registrations sharing only a name are not matched at all: 0 of 15 labelled pairs were one Carrier. Against GLEIF, the same pair stays a Possible Match.
- **One Registration, at most one LEI.** A Registration as strongly matched to several GLEIF records is matched to none of them firmly.
- **Portfolio names follow a looser rule.** A Portfolio name is Firm when exactly one Entity has its exact normalised name, within the state and city when the analyst gives them. It needs no corroborating signal, because the analyst typed a name and usually nothing else to corroborate it with. Near names scoring at least 0.8 are offered as up to three Possible Matches beside it. This is safe only because the analyst sees every Match with its evidence, and a Verdict can reject it; a wrong Firm Match between two Source Records is never shown that way.

**Against.** *Splink* (Fellegi-Sunter on DuckDB): more principled, but its unsupervised EM training is known to behave badly when true matches are a tiny fraction of candidate pairs, which is the FMCSA-to-GLEIF case, and learned weights are harder to defend than a rule I wrote. *Embeddings*: `ABC Trucking` and `ABD Trucking` are near neighbours; that is the wrong notion of similar. *The `rapidfuzz` community extension*: works, but community extensions download at runtime and that is a fragile step in a clean clone. *Destructive merging*: reasoning about a tidied copy hides exactly the mess the analyst needs to see.

**Cost.** Thresholds are hand-picked, not calibrated. Subset names (`PEPSI` / `PEPSI BOTTLING GROUP`) land in Possible rather than Firm. Sorting tokens makes `J & H EXPRESS` equal `H & J EXPRESS`. Every query pays a cluster indirection. **Where the rule is wrong:** two franchisees of one brand, each under its own legal name that includes the brand, in the same ZIP become one Entity, producing a false **Hidden Concentration**; the analyst can reject it with a Verdict, but only if they look. In Pass B, most corroborated Possible Matches are a parent and its subsidiary at one address, not one Entity.

**Mitigation.** ~100 hand-labelled pairs sampled across the bands, measured precision reported in the README.

**Would change my mind.** A few thousand labelled pairs (then Splink with supervised weights wins), or analyst Verdicts accumulating at volume (same thing, for free).

## 4. The slice

**Chose.** GLEIF: entities with a US legal or headquarters address (383,816 in the 2026-09-18 snapshot), all corporate consolidation edges worldwide with their endpoint entities (ownership chains leave the country), and reporting exceptions for those entities. Fund relationships skipped. FMCSA: `power_units >= 10`, any status, plus out-of-service orders for those numbers. Shipped as a committed Parquet snapshot; `make ingest` rebuilds it.

**Against.** *Everything*: 5.7 GB and 4.5M rows, and an ingestion pipeline is not the product. *One industry or one state*: ownership chains and fleets cross both. *Active carriers only*: deletes the out-of-service-then-reregistered pattern.

**Cost.** The 10-unit floor drops ~95% of FMCSA. That reincarnation pattern is concentrated among small carriers, so the slice under-samples the very phenomenon it shows off. The snapshot ages and makes the repository heavy.

**At fifty times the volume, in the order I expect it to break:** (1) blocking, because pair counts grow quadratically inside a block; watch the block-size histogram at ingest, fix with multi-key and rare-token blocking and a block-size cap. (2) transitive clusters, because more records mean more bad bridges; watch the cluster-size distribution. (3) the fixed **Agent Address** threshold, which should become relative to local density. (4) the committed snapshot, which moves to object storage with delta ingest. Storage and traversal are last: ownership edges grow about 2x, not 50x. I believe that; I have not tested it.

## 5. Shared address as a Common Cause, and the Agent Address rule

**Chose.** Only GLEIF *headquarters* and FMCSA *physical* addresses count. An address shared by more than ~10 Entities is an **Agent Address**: not evidence for a Match, not a Common Cause, and its frequency is shown to the analyst.

**Against.** Using legal and mailing addresses: thousands of unrelated companies share one registered-agent address in Delaware, and a naive rule flags half of any Portfolio as one concentration.

**Cost.** A real industrial park with fifteen tenants is discounted too, and that is the motivating example. Geocoding plus parcel data would separate the two cases; out of scope.

**Jurisdiction is ranked last.** A shared legal jurisdiction is listed after every Ultimate Parent and address Concentration, however large its share. In a 25-name food-and-beverage test Portfolio, 52% of it was incorporated in Delaware. Ranked by share alone, that would be the headline finding, and it tells an analyst almost nothing. It stays in the list because a change in one state's law does reach every company incorporated there.

## 6. Ultimate Parent: walk the chain, do not trust the shortcut

**Chose.** Walk direct Ownership Links to the top. Fall back to the **Declared Ultimate Parent** where the chain breaks. Count and surface disagreements.

**Against.** Using the declared ultimate edge alone: one hop, simpler, but it turns the required multi-hop traversal into a lookup and hides intermediate holding companies, which are themselves where a group collapse lands.

**Cost.** Cycle and broken-chain handling, and an answer that is sometimes "these two sources disagree".

## 7. Interface: three fixed screens, no explorer, no chat

**Chose.** Portfolio (match review with evidence and confirm/reject) → Exposure (one CPO sentence, ranked concentrations marked firm or tentative, unverifiable-ownership count) → Concentration detail (ownership path diagram, Registrations and their status, As-Of Dates). Verdicts persist per Portfolio.

**Against.** A force-directed graph explorer: looks like a graph product and tells an analyst nothing. A natural-language query box: the questions are few and known, and a wrong generated query is a hidden failure. Global Verdict feedback: the right product, but it needs multi-tenant trust rules.

**Cost.** The analyst cannot browse. The tool answers one question.

## 8. No LLM at runtime

**Chose.** Deterministic resolution. LLM adjudication of the Possible band only, offline, with cached verdicts committed so a clean clone needs no key, as the first stretch item and the first thing cut.

**Against.** An LLM across all candidate pairs: neither cheap nor auditable at a million pairs. At five hundred ambiguous pairs with both records in view, it is both.

**Would change my mind.** Measured precision in the Possible band so poor that the analyst's review queue is unusable.

## 9. Stack: FastAPI and React

**Chose.** FastAPI and React with TypeScript. Python keeps the resolution work next to the database and its data tooling; a typed frontend keeps three screens of match evidence honest. No strong counter-argument for this shape of application. The alternative considered was a single Next.js application (one deploy), rejected because the resolution work wants Python's data tooling next to the database.

## Cut order, decided in advance

LLM adjudication → Verdict persistence (keep the buttons, hold state in session) → jurisdiction Common Cause → out-of-service join (keep census status only) → "confirm all" conveniences. Never cut: three-state **Ownership Status**, Match evidence in the interface, the measured precision number, the five documents.
