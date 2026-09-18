# Decision log

Each entry: what I chose, what I chose against and why not, what it cost, what would change my mind. Terms in **bold** are defined in `CONTEXT.md`.

## 1. Outcome: Tier 2/3 Supplier Intelligence, reframed as Hidden Concentration discovery

**Chose.** Given a **Portfolio**, find members that look independent but share a **Common Cause**. See `ASSUMPTIONS.md` gap 1 for why it is not literally "Tier 2/3".

**Against.** *Geographic Supplier Risk*: a map is the deliverable, and geocoding ~100k messy addresses would eat the budget. *Supplier Risk Intelligence*: continuous scoring needs a time series; from one snapshot, a score is an invented weighted sum I could not defend past the first "why".

**Cost.** No map, so the motivating example (a flood closes an industrial park) is not served. No single per-supplier number for the CPO.

**As built.** The reframing held up, but mostly for companies that appear in both registries. The curated sample of 15 food and beverage makers finds 4 Hidden Concentrations and 1 tentative one. A random list of 15 private-fleet operators finds none, with ownership unverifiable for 14 of them. Only 2.1% of Registrations join firmly to a GLEIF record.

**Would change my mind.** Historical snapshots of the FMCSA census (then degradation-over-time becomes real and scoring becomes defensible).

## 2. Storage: DuckDB with recursive CTEs

See `docs/adr/0001-duckdb-as-the-graph-store.md`.

**Chose.** One DuckDB file. Traversal by recursive CTE with a cycle guard and depth cap.

**Against.** *Neo4j*: one traversable edge type and shallow chains, so Cypher buys little and costs a server in the clean-clone path. *Postgres*: nothing is transactional except **Verdicts**.

**Cost.** Single writer. No graph query language, so every new traversal is hand-written SQL. DuckPGQ (SQL/PGQ) could not be relied on: the community extension failed to download for the current DuckDB version when tested.

**As built.** The graph is not kept in a DuckDB file. The snapshot is loaded into memory and resolved at every start-up, which takes about 8 seconds and means a rule change needs no migration. Only Portfolios and Verdicts are written to disk. The one traversal needed, the ownership walk, is one recursive CTE of about 70 lines, cycle and broken-chain handling included.

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

**Mitigation.** 102 Matches sampled across the bands, labelled, and the precision per band reported in the README. The labels were made by an AI assistant, not by a person (`AI_LOG.md` entry 2), so the figures measure agreement with one careful reader. Firm Matches were right in 33 of the 33 decided pairs. In Pass B the Possible band was right 5 times in 15 when corroborated and 9 times in 16 on name alone, which is why it is shown to the analyst and never used to build Entities.

**Would change my mind.** A few thousand labelled pairs (then Splink with supervised weights wins), or analyst Verdicts accumulating at volume (same thing, for free).

## 4. The slice

**Chose.** GLEIF: entities with a US legal or headquarters address (383,816 in the 2026-09-18 snapshot), all corporate consolidation edges worldwide with their endpoint entities (ownership chains leave the country), and reporting exceptions for those entities. Fund relationships skipped. FMCSA: `power_units >= 10`, any status, plus out-of-service orders for those numbers. Shipped as a committed Parquet snapshot; `make ingest` rebuilds it.

**Against.** *Everything*: 5.7 GB and 4.5M rows, and an ingestion pipeline is not the product. *One industry or one state*: ownership chains and fleets cross both. *Active carriers only*: deletes the out-of-service-then-reregistered pattern.

**Cost.** The 10-unit floor drops about 96% of FMCSA: the slice keeps 192,915 of the census's 4,502,467 rows (counted 2026-09-18). That reincarnation pattern is concentrated among small carriers, so the slice under-samples the very phenomenon it shows off. The snapshot ages and makes the repository heavy.

**At fifty times the volume, in the order I expect it to break:** (1) blocking, because pair counts grow quadratically inside a block; watch the block-size histogram at ingest, fix with multi-key and rare-token blocking and a block-size cap. (2) transitive clusters, because more records mean more bad bridges; watch the cluster-size distribution. (3) the fixed **Agent Address** threshold, which should become relative to local density. (4) the committed snapshot, which moves to object storage with delta ingest. Storage and traversal are last: ownership edges grow about 2x, not 50x. I believe that; I have not tested it.

**As built.** The first warning is already visible at this size. Two blocking keys exceed the 1,000-record cap and are skipped (names starting `CAPITAL ` in New York and in California), so records in them are never matched. Candidate pairs total about 3.4 million. No Entity exceeds 25 records, and the whole resolution runs in about 7 seconds. `make resolve` prints both histograms, so the early warnings are one command away.

## 5. Shared address as a Common Cause, and the Agent Address rule

**Chose.** Only GLEIF *headquarters* and FMCSA *physical* addresses count. An address shared by more than ~10 Entities is an **Agent Address**: not evidence for a Match, not a Common Cause, and its frequency is shown to the analyst.

**Against.** Using legal and mailing addresses: thousands of unrelated companies share one registered-agent address in Delaware, and a naive rule flags half of any Portfolio as one concentration.

**Cost.** A real industrial park with fifteen tenants is discounted too, and that is the motivating example. Geocoding plus parcel data would separate the two cases; out of scope.

**As built.** The threshold is more than 10 distinct names. The snapshot has 4,400 such addresses. The largest, `251 LITTLE FALLS DR 19808` in Wilmington, carries 4,505 names. The detail screen shows how many names are registered at a shared address and who they are, so an analyst can judge a site that falls just under the line.

**Jurisdiction is ranked last.** A shared legal jurisdiction is listed after every Ultimate Parent and address Concentration, however large its share. In a 25-name food-and-beverage test Portfolio, 52% of it was incorporated in Delaware. Ranked by share alone, that would be the headline finding, and it tells an analyst almost nothing. It stays in the list because a change in one state's law does reach every company incorporated there.

## 6. Ultimate Parent: walk the chain, do not trust the shortcut

**Chose.** Walk direct Ownership Links to the top. Fall back to the **Declared Ultimate Parent** where the chain breaks. Count and surface disagreements.

**Against.** Using the declared ultimate edge alone: one hop, simpler, but it turns the required multi-hop traversal into a lookup and hides intermediate holding companies, which are themselves where a group collapse lands.

**Cost.** Cycle and broken-chain handling, and an answer that is sometimes "these two sources disagree".

## 7. Interface: three fixed screens, no explorer, no chat

**Chose.** Portfolio (match review with evidence and confirm/reject) → Exposure (one CPO sentence, ranked concentrations marked firm or tentative, unverifiable-ownership count) → Concentration detail (ownership path diagram, Registrations and their status, As-Of Dates). Verdicts persist per Portfolio.

**Against.** A force-directed graph explorer: looks like a graph product and tells an analyst nothing. A natural-language query box: the questions are few and known, and a wrong generated query is a hidden failure. Global Verdict feedback: the right product, but it needs multi-tenant trust rules.

**Cost.** The analyst cannot browse. The tool answers one question.

**As built.** A first-time user needs names to paste, so the landing page offers a sample. It is curated, which means it finds what it was chosen to find, and the interface says so. Beside it the page shows what a random list of the same size finds (nothing), so the sample's result cannot be read as typical.

## 8. No LLM at runtime

**Chose.** Deterministic resolution. LLM adjudication of the Possible band only, offline, with cached verdicts committed so a clean clone needs no key, as the first stretch item and the first thing cut.

**Against.** An LLM across all candidate pairs: neither cheap nor auditable at a million pairs. At five hundred ambiguous pairs with both records in view, it is both.

**Would change my mind.** Measured precision in the Possible band so poor that the analyst's review queue is unusable.

**As built.** Cut: it was first in the cut order. The measurement now argues for it: in Pass B the Possible band is right 33% of the time when corroborated and 56% on name alone. Those pairs are where an analyst's time goes, and the most common error, a parent and its subsidiary at one address, is one a model reading both records could name. It is the first thing to build next.

## 9. Stack: FastAPI and React

**Chose.** FastAPI and React with TypeScript. Python keeps the resolution work next to the database and its data tooling; a typed frontend keeps three screens of match evidence honest. No strong counter-argument for this shape of application. The alternative considered was a single Next.js application (one deploy), rejected because the resolution work wants Python's data tooling next to the database.

**Cost.** A clean clone needs two toolchains, uv and Node.js, and the interface must be built before `make serve` shows it. Every API shape is written twice, as a Pydantic model and as a TypeScript type, and nothing checks that the two agree.

**Would change my mind.** A team whose other services are all TypeScript, or an interface small enough to render on the server with no build step.

## 10. A Concentration counts only what is firm

**Chose.** A Concentration's share counts only members whose Match is Firm or confirmed. It is **tentative** unless two different Entities reach it that way, and the share it would have if every Possible Match held is shown beside it. Two Portfolio names that resolve to one Entity are one company, not a Concentration. A Verdict is stored against the Source Record its Match was made through (an LEI or a USDOT number), not against the Entity id.

**Against.** Counting every Possible Match: in the sample, 9 members would be affected rather than 7. The extra two are Rolling Frito-Lay and Naked Juice under PepsiCo, and that group rests on "Naked Juice LLC", a name two different Entities hold exactly. Until the analyst says which, it is a guess. Keying Verdicts to Entity ids: simpler, but Entity ids are recomputed every time the snapshot is resolved, so a Verdict would quietly stop applying after a rebuild.

**Cost.** The headline figure is lower than the evidence may support. An analyst who does not work through the undecided names sees less exposure than there is.

**Would change my mind.** Possible-band precision high enough (from LLM adjudication or accumulated Verdicts) that counting a Possible Match is more often right than wrong.

## Cut order, decided in advance

LLM adjudication → Verdict persistence (keep the buttons, hold state in session) → jurisdiction Common Cause → out-of-service join (keep census status only) → "confirm all" conveniences. Never cut: three-state **Ownership Status**, Match evidence in the interface, the measured precision number, the five documents.

**What was cut.** The two ends of the list: LLM adjudication and the "confirm all" conveniences, so each Match is decided one at a time. Verdict persistence, the jurisdiction Common Cause and the out-of-service join were all built. Not planned but also not built: delta ingest and Supply Links from USAspending, both drawn in `docs/architecture/`.
