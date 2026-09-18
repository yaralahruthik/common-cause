# AI log

## 1. "DuckDB has no Jaro-Winkler" (2026-09-18)

**What happened.** I asked Claude Code to check which string-similarity primitives DuckDB offers before committing to in-database matching. Its probe listed functions with `WHERE function_name ~ 'jaro|levensh|...'` and got back only `hamming`, `jaccard`, `strip_accents`. Taken at face value: DuckDB has no Jaro-Winkler or Levenshtein, so matching has to move to Python or a community extension.

**How it was caught.** The same script then *called* `jaro_winkler_similarity(...)` and it returned 0.967. A function that runs cannot be missing. DuckDB's `~` is a full-string match, not a search, so the filter only kept names equal to one of the alternatives. Re-run with `regexp_matches`, the full list appeared.

**Why it matters.** The wrong reading would have reversed decision 3 (core functions only, no runtime extension download).

## Watch items, not yet incidents

- The research agent's GLEIF relationship-type shares (fund ~50%, consolidation ~50%) were extrapolated from the first ~60k rows of a file it also described as sorted. A head sample of a sorted file is not a random sample. To be checked against full-file counts during ingest; `ASSUMPTIONS.md` gap 2 carries the caveat until then.
