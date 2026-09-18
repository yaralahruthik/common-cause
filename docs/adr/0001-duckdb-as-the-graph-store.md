---
status: accepted
---

# DuckDB as the graph store, not a graph database

The graph (~600k Entities, ~250k Ownership Links in the slice) lives in a single DuckDB file, and multi-hop traversal is done with recursive CTEs. The workload is bulk load from wide registry CSVs followed by analytical reads: ancestor walks up shallow ownership chains, and group-bys on shared Ultimate Parent, address and jurisdiction. That is a columnar-analytics shape, and DuckDB also gives a zero-server clean clone, direct reads of the source files, and in-engine string similarity for Match scoring.

## Considered Options

- **Neo4j**: rejected because there is only one traversable edge type and the chains are shallow, so Cypher buys little while costing a server in the clean-clone path. It wins if real Supply Links arrive and queries become variable-length paths across many edge types.
- **Postgres with recursive CTEs**: rejected because nothing here is transactional except Verdicts. It wins once there are multi-user writes or daily delta upserts.

## Consequences

Single-writer: Portfolios and Verdicts are the only runtime writes and must go through one connection. Entity resolution runs as SQL inside the engine rather than as Python loops.

As built, the graph is not itself kept in a DuckDB file. The committed Parquet snapshot is loaded into an in-memory database at start-up and resolved there, so a rule change needs no migration. Portfolios and Verdicts, which must outlive a restart, live in a separate DuckDB file (`data/workspace.duckdb`) attached to that same connection, and a lock makes the connection the only writer. Each request also rebuilds a few temporary tables on that connection, which the lock serialises too.
