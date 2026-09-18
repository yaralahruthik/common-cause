"""Ultimate Parents, found by walking direct Ownership Links up to the top (DECISIONS.md entry 6).

Writes `ultimate_parent`: one row per GLEIF record with the LEI it rolls up to, the path walked, and how far the
walk can be trusted.

- `basis` is `walked` when the chain of direct links reached a company that declares no parent; `declared` when
  the chain broke and the registry's Declared Ultimate Parent stands in; `partial walk` when it broke and nothing
  was declared, so the furthest point reached stands in.
- `chain_break` says why: `cycle` (the walk came back to a company already on it), `depth cap` (still climbing
  after MAX_CHAIN_HOPS), or `missing direct link` (the top of the walk declares an Ultimate Parent it has no
  direct link towards).
- `disagrees` marks a complete walk whose top is not the company's own Declared Ultimate Parent. The walk wins;
  the disagreement is a finding.
"""

import duckdb

# GLEIF chains are shallow; a walk still climbing after this many hops is treated as broken.
MAX_CHAIN_HOPS = 20

ULTIMATE_PARENT_SQL = """
create or replace table ultimate_parent as
with recursive
direct_link as (
    select child_lei as lei, min(parent_lei) as parent_lei
    from gleif_ownership_link
    where relationship_type = 'IS_DIRECTLY_CONSOLIDATED_BY' and relationship_status = 'ACTIVE'
        and child_lei <> parent_lei
    group by all
),
declared as (
    select child_lei as lei, min(parent_lei) as parent_lei
    from gleif_ownership_link
    where relationship_type = 'IS_ULTIMATELY_CONSOLIDATED_BY' and relationship_status = 'ACTIVE'
        and child_lei <> parent_lei
    group by all
),
walk(lei, path, chain_break) as (
    select lei, [lei], null::varchar from gleif_record
    union all
    select
        walk.lei,
        list_append(walk.path, direct_link.parent_lei),
        case
            when list_contains(walk.path, direct_link.parent_lei) then 'cycle'
            when len(walk.path) > $max_hops then 'depth cap'
        end
    from walk
    join direct_link on direct_link.lei = walk.path[-1]
    where walk.chain_break is null
),
terminal as (
    select lei, arg_max({'path': path, 'chain_break': chain_break}, len(path)) as walked
    from walk
    group by lei
),
classified as (
    select
        terminal.lei,
        walked.path,
        case
            when walked.chain_break is null and top_declared.parent_lei is not null then 'missing direct link'
            else walked.chain_break
        end as chain_break,
        declared.parent_lei as declared_ultimate_parent_lei,
        top_declared.parent_lei as top_declared_lei,
        -- Inside a cycle every company is someone's parent, so the smallest LEI on it stands for all of them.
        case
            when walked.chain_break = 'cycle' then list_min(walked.path[list_position(walked.path, walked.path[-1]):])
            else walked.path[-1]
        end as furthest_lei
    from terminal
    left join declared using (lei)
    left join declared as top_declared on top_declared.lei = terminal.walked.path[-1]
)
select
    lei,
    case
        when chain_break is null then path[-1]
        else coalesce(declared_ultimate_parent_lei, top_declared_lei, furthest_lei)
    end as ultimate_parent_lei,
    case
        when chain_break is null then 'walked'
        when coalesce(declared_ultimate_parent_lei, top_declared_lei) is not null then 'declared'
        else 'partial walk'
    end as basis,
    chain_break,
    path,
    declared_ultimate_parent_lei,
    coalesce(chain_break is null and declared_ultimate_parent_lei <> path[-1], false) as disagrees
from classified
"""


def build_ownership(con: duckdb.DuckDBPyConnection) -> None:
    """Builds `ultimate_parent` from the snapshot tables already loaded into `con`."""
    con.execute(ULTIMATE_PARENT_SQL, {"max_hops": MAX_CHAIN_HOPS})


def chain_summary(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str, int, int]]:
    """GLEIF records by how their Ultimate Parent was found: basis, chain break, records, and disagreements."""
    return con.sql(
        """
        select basis, coalesce(chain_break, ''), count(*), count(*) filter (where disagrees)
        from ultimate_parent group by all order by all
        """
    ).fetchall()  # type: ignore[return-value]
