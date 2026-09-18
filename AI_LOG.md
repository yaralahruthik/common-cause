# AI log

## 1. "DuckDB has no Jaro-Winkler" (2026-09-18)

**What happened.** I asked Claude Code to check which string-similarity primitives DuckDB offers before committing to in-database matching. Its probe listed functions with `WHERE function_name ~ 'jaro|levensh|...'` and got back only `hamming`, `jaccard`, `strip_accents`. Taken at face value: DuckDB has no Jaro-Winkler or Levenshtein, so matching has to move to Python or a community extension.

**How it was caught.** The same script then *called* `jaro_winkler_similarity(...)` and it returned 0.967. A function that runs cannot be missing. DuckDB's `~` is a full-string match, not a search, so the filter only kept names equal to one of the alternatives. Re-run with `regexp_matches`, the full list appeared.

**Why it matters.** The wrong reading would have reversed decision 3 (core functions only, no runtime extension download).

## 2. The precision labels were made by the assistant (2026-09-18)

**What happened.** Measuring match precision needed about 100 hand-labelled pairs. With my agreement, Claude Code sampled 102 Matches and labelled each one itself. It read both records, their addresses and the evidence line, and used what it knew about the companies (for example, that Wright Service Corp. is the parent of Wright Tree Service). Each label carries a one-line reason.

**How it is contained.** The README says who labelled the pairs and what "same" meant. The labels are committed, so anyone can overwrite one and re-run `make resolve`. Every label's note gives its reason, so a label resting on outside knowledge can be found and checked. Where the reasoning was not enough to decide, the label is `unsure`. I have not verified the labels myself.

**Why it matters.** A model grading pairs produced by rules the same model wrote is not an independent check. The figure measures consistency with one careful reader, not ground truth. The first sample was also used to find rule defects, so a fresh sample was drawn before labelling.

## Watch items, not yet incidents

- The research agent's GLEIF relationship-type shares (fund ~50%, consolidation ~50%) were extrapolated from the first ~60k rows of a file it also described as sorted. A head sample of a sorted file is not a random sample. **Checked during ingest (2026-09-18):** the full file has 53.2% consolidation and 46.4% fund records, so the estimate was close. It was close by luck, not by method. `ASSUMPTIONS.md` gap 2 now carries the full-file counts.
