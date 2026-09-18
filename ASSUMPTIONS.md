# Assumptions

Each entry: what was unclear, what I decided, why, and what I would need to know to decide differently. Ordered by how much damage the gap does if taken at face value. Terms in **bold** are defined in `CONTEXT.md`.

## 1. None of the sources contains a supplier relationship

**Unclear.** The problem statement asks for "Tier 2 and Tier 3" visibility and "who supplies their suppliers", then supplies GLEIF (who *owns* whom), FMCSA (who *runs trucks*, no edges at all) and Open Supply Hub (see gap 4). A **Tier** is defined over **Supply Links**. There are none in the data.

**Decided.** An **Ownership Link** is never treated as a **Supply Link**, and ownership hops are never called Tiers. The outcome is reframed: the user brings their known direct relationships as a **Portfolio**, and the graph finds **Hidden Concentrations**, members that look independent but share a **Common Cause** (one **Ultimate Parent**, one physical address, one jurisdiction).

**Why.** Walking three GLEIF parent hops and labelling the result "Tier 3 suppliers" produces a confident, plausible and wrong answer. The reframing is still the thing the glossary calls the concentration risk that matters most: "several suppliers who all depend on the same upstream source."

**Would change my mind.** A loadable source of real supply edges. The best free candidate found is USAspending prime-to-subaward records (structured, real contractual edges, US federal only). Customs bill-of-lading data is the true answer and is not freely available in bulk.

## 2. "Broadly one parent record per registered entity" is not true

**Unclear.** The problem statement says to expect GLEIF relationship edges to track the entity count. Counted in full on the 2026-09-18 Golden Copy: 3,434,096 entities, 488,309 relationship records, 6,362,498 reporting exceptions. Of the relationship records, 259,753 (53.2%) are corporate consolidation edges (126,784 direct, 132,969 ultimate), 226,597 (46.4%) are fund structures (fund-managed-by, sub-fund, feeder) and 1,959 (0.4%) are international branches. Most entities file an *exception* in place of a parent.

**Decided.** Absence of an Ownership Link is never read as independence. Every **Entity** carries an **Ownership Status**: **Declared Parent** (an active consolidation edge), **Declared Independent** (every exception reason given is `NATURAL_PERSONS` or `NON_CONSOLIDATING`) or **Undisclosed Parent** (any other reason, such as `NO_LEI`, `NO_KNOWN_PERSON`, `NON_PUBLIC` and its newer variants like `CONSENT_NOT_OBTAINED`, or no filing at all). About 7,000 direct-parent exceptions in the full file give several reasons (195 in the slice), most often `NATURAL_PERSONS` alongside `NO_KNOWN_PERSON`; one hedged reason is enough to make independence unverifiable. The direct-parent exception is read before the ultimate-parent one. The interface always reports how much of a Portfolio is unverifiable.

In the snapshot's 383,816 entities with a US legal or headquarters address, 20,453 (5.3%) have a Declared Parent, 197,584 (51.5%) are Declared Independent and 165,779 (43.2%) have an Undisclosed Parent.

**Why.** "No concentration found" over a graph where most nodes have no parent edge is a false reassurance, which is the worst thing a risk tool can emit.

**Would change my mind.** An ownership source that covers private companies, such as beneficial-ownership filings, would shrink the Undisclosed Parent share; the three-state model stays.

## 3. "Near real time" from sources that publish daily

**Unclear.** The problem statement asks for near-real-time freshness and, in the next sentence, says the sources publish daily. (GLEIF actually publishes three times a day with delta files; the FMCSA census was last updated four days before I checked.)

**Decided.** Freshness is bounded by source cadence. Every fact carries an **As-Of Date**, shown in the interface. Only batch load is built. Delta ingestion (GLEIF 8-hour deltas, Socrata `:updated_at`) is designed and drawn, not built. **Staleness** is surfaced as a risk signal rather than cleaned.

**Why.** Claiming real-time over a daily file is a lie the first analyst will catch. A lapsed registration or a decade-old filing is information.

**Would change my mind.** A push or streaming feed from either registry, or a customer's own transactional data joining the graph.

## 4. Open Supply Hub is not usable, and would not mean what the problem statement implies

**Unclear.** Listed as the closest analogue to a commercial supply relationship, with a 5,000-location cap.

**Decided.** Dropped. Every API path returns 401 without an account, API keys start at $2,700 a year, and OS Hub's own data-model page says a contributor link means the organisation *shared data about* a facility, not that it sources from it.

**Would change my mind.** Filtering to brand-type contributors publishing their own supplier lists would give suggestive Supply Links. Worth an afternoon with a nonprofit key; not worth an hour of the initial build.

## 5. FMCSA is called "the transport layer", but its value here is elsewhere

**Unclear.** The problem statement frames FMCSA as trucking companies. Only 76 US GLEIF entities have "TRUCKING" in their legal name, so matching for-hire carriers to GLEIF yields almost nothing. FMCSA carries no LEI, EIN or parent field.

**Decided.** FMCSA is treated as an operational-footprint registry. It lists every company that runs trucks, including manufacturers' and distributors' private fleets, which are exactly the **Suppliers** in a procurement Portfolio. A **Carrier** is any Entity holding a **Registration**. The measured cross-source match rate is reported in the README whatever it turns out to be.

**Would change my mind.** A measured match rate so low that the cross-source join is decorative. Then the honest system is two graphs and a shared interface.

## 6. There is no customer, so there is no "my suppliers"

**Decided.** The user pastes or uploads a Portfolio of names. A bundled sample shaped like a food-and-beverage manufacturer's list is provided, built from what the data contains and disclosed as curated, alongside what a random Portfolio shows.

**Would change my mind.** Access to a real supplier master file, which would also supply addresses and make **Firm Matches** reachable far more often.

## 7. Which user

**Decided.** The Supply Chain Risk Analyst. The CPO gets one sentence at the top of the analyst's screen, not a separate dashboard. Analysts need to see why two records were matched, which forces the evidence trail that makes the tool usable without me.

## 8. "One operator under several numbers" is a signal, not a mess

**Decided.** Several Registrations resolve to one Entity, but each Registration keeps its own status. An Entity showing "3 Registrations, 1 out of service, 1 registered shortly after" is the degradation signal; merging the rows and keeping one status would erase it.
