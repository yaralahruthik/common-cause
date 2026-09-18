# AI log

## 1. "DuckDB has no Jaro-Winkler" (2026-09-18)

**What happened.** I asked Claude Code to check which string-similarity primitives DuckDB offers before committing to in-database matching. Its probe listed functions with `WHERE function_name ~ 'jaro|levensh|...'` and got back only `hamming`, `jaccard`, `strip_accents`. Taken at face value: DuckDB has no Jaro-Winkler or Levenshtein, so matching has to move to Python or a community extension.

**How it was caught.** The same script then *called* `jaro_winkler_similarity(...)` and it returned 0.967. A function that runs cannot be missing. DuckDB's `~` is a full-string match, not a search, so the filter only kept names equal to one of the alternatives. Re-run with `regexp_matches`, the full list appeared.

**Why it matters.** The wrong reading would have reversed decision 3 (core functions only, no runtime extension download).

## 2. The precision labels were made by the assistant (2026-09-18)

**What happened.** Measuring match precision needed about 100 hand-labelled pairs. With my agreement, Claude Code sampled 102 Matches and labelled each one itself. It read both records, their addresses and the evidence line, and used what it knew about the companies (for example, that Wright Service Corp. is the parent of Wright Tree Service). Each label carries a one-line reason.

**How it is contained.** The README says who labelled the pairs and what "same" meant. The labels are committed, so anyone can overwrite one and re-run `make resolve`. Every label's note gives its reason, so a label resting on outside knowledge can be found and checked. Where the reasoning was not enough to decide, the label is `unsure`. I have not verified the labels myself.

**Why it matters.** A model grading pairs produced by rules the same model wrote is not an independent check. The figure measures consistency with one careful reader, not ground truth. The first sample was also used to find rule defects, so a fresh sample was drawn before labelling.

## 3. "Large trucking groups truly look like this" (2026-09-18, planning)

**What happened.** While choosing an outcome, Claude Code proposed the headline demo: "You contract with six carriers. Four of them belong to one parent group." It backed this up with "Large trucking groups truly look like this", and said GLEIF gives "real, directed, multi-hop edges". I agreed, and the plan was built on for-hire trucking groups.

**How it was caught.** A background research agent looked the groups up in GLEIF. Knight-Swift, Werner and XPO each file a `NON_CONSOLIDATING` exception and list no subsidiaries. Schneider National files `NO_KNOWN_PERSON`. The committed snapshot shows the same today. About 20 minutes after the claim, the assistant retracted it: "one part of my round 1 advice was wrong … GLEIF does not hold those links."

**Why it matters.** The whole product rested on it. It is why FMCSA is treated as a register of anyone who runs trucks, private fleets included, rather than of trucking companies (`ASSUMPTIONS.md` gap 5). It is also why the sample is food and beverage makers and why every Entity carries a three-state Ownership Status. The claim was plausible and fluent, and it had not been checked against a single record.

## 4. Verdicts that would quietly stop applying (2026-09-18, Hidden Concentrations)

**What happened.** The first version of the Portfolio code stored each Verdict against an Entity id. The assistant summarised it as "Verdicts: saved per Portfolio". But an Entity id is the smallest record id among the Entity's Source Records, recomputed every time the snapshot is resolved. After a rebuild that regrouped an Entity, a stored Verdict would match nothing, without any error.

**How it was caught.** A review agent, asked to check the change against the spec, flagged it. The same review found three more errors in the concentration rules:
- a Concentration marked firm counted a Possible member in its share;
- a member with no Firm Match was counted as unverifiable ownership, when it is not yet known which company it is;
- two names that resolve to one Entity formed a Concentration on every cause.

Separately, running a food-and-beverage Portfolio showed Delaware ranked first at 52%.

**What changed.** Verdicts are now keyed to the LEI or USDOT number the Match was made through. Each rule was fixed with a test in `tests/test_exposure.py`, and jurisdictions are ranked last (`DECISIONS.md` entries 5 and 10). All of these were fixed in commit `b826bb3`.

## 5. 100% precision while Firm Matches bridged two companies (2026-09-18, entity resolution)

**What happened.** The labelled sample gave Firm Matches 17 of 17 in Pass A and 16 of 16 in Pass B. Read at face value, the Firm band was clean.

**How it was caught.** A structural query, not the sample. An LEI identifies one legal entity, so no Entity should hold two. `select count(*) from entity where gleif_records > 1` returned 79, among them Valvoline LLC with VALVOLINE INC. and CUMMINS INC. with CUMMINS LTD. In each, one Registration had been firmly matched to several LEIs. A 17-pair sample cannot see a defect of about 2%.

**What changed.** A Registration that matches several LEIs equally strongly is now firmly matched to none of them, and an Entity still holding two LEIs is flagged `several_leis`. Two such Entities remain. Tests: `test_a_registration_that_firmly_matches_two_gleif_records_matches_neither_firmly` and `test_an_entity_reaching_two_gleif_records_through_registrations_is_flagged`. The README now says what 17 pairs per band can and cannot show.

## 6. "The full flow runs with no console errors" (2026-09-18, interface)

**What happened.** Before committing the interface, the assistant reported "The full flow runs with no console errors", then "All green. Running the review now." It had shortened ownership paths that loop but checked only the last step. A path such as A → B → C → B survived, and the ownership tree layout recursed until the stack overflowed, which left the detail screen blank.

**How it was caught.** The code-review agent read the path code and found 7 GLEIF records in the real `ultimate_parent` table that trigger the loop. The same review found three smaller bugs, including a "would be N if X is confirmed" sentence that named the wrong members.

**What changed.** A path now never repeats a company (`test_a_path_through_a_cycle_stops_at_the_ultimate_parent_and_never_repeats_a_company`), and the tree layout places each company once, however many members pass through it (`web/src/tree.ts`). All of this was fixed before the interface was committed.

## 7. A fix for a number that was never in the code (2026-09-18, interface)

**What happened.** While planning the interface, the assistant said the existing API "reports 8 members 'in a concentration, firm'" for the sample and that this should be 7. It filed that as a fix on the issue. The commit that added the interface says members in only a tentative Concentration are "no longer counted (7 of 15 in the sample, not 8)", and the pull request says the same.

**How it was caught.** The assistant ran the real API on the sample and found no such field. The figure 8 came from mock data another agent had generated for the interface design. The assistant's closing summary said so: "The old wrong figure wasn't in the code … there was nothing to correct."

**What did not change.** The commit message of `f414d47` and the text of pull request #9 still describe the change as a correction. The `affected` count it introduced is new, not fixed. Merged history is left as it is, and this entry is the correction.

## Watch items, not yet incidents

- The research agent's GLEIF relationship-type shares (fund ~50%, consolidation ~50%) were extrapolated from the first ~60k rows of a file it also described as sorted. A head sample of a sorted file is not a random sample. **Checked during ingest (2026-09-18):** the full file has 53.2% consolidation and 46.4% fund records, so the estimate was close. It was close by luck, not by method. `ASSUMPTIONS.md` gap 2 now carries the full-file counts.
