"""What resolution produced: the numbers `make resolve` prints and the README reports."""

import csv
import io
from itertools import pairwise
from pathlib import Path

import duckdb

from common_cause.resolve.resolution import MAX_BLOCK_RECORDS

# Hand-labelled Match pairs, committed so the precision figure can be re-measured after any rule change.
DEFAULT_LABELS_PATH = Path(__file__).resolve().parents[3] / "data" / "labels" / "match_labels.csv"

# Bucket upper bounds for the size histograms.
SIZE_BUCKETS = (1, 2, 5, 10, 25, 100, MAX_BLOCK_RECORDS)

# Precision is reported per stratum: the name-only Possible band behaves nothing like the corroborated one.
STRATUM_SQL = """
case
    when band = 'Firm' then 'Firm'
    when same_zip or same_phone or len(shared_officers) > 0 or prior_revoke then 'Possible, corroborated'
    else 'Possible, name only'
end
"""


def size_histogram(con: duckdb.DuckDBPyConnection, table: str, column: str) -> list[tuple[str, int]]:
    """Rows of `table` counted by `column`, in buckets: [("1", n), ("2", n), ("3-5", n), ...]."""
    bounds = [0, *SIZE_BUCKETS]
    labels = [str(high) if high - low == 1 else f"{low + 1}-{high}" for low, high in pairwise(bounds)]
    labels.append(f">{SIZE_BUCKETS[-1]}")
    counts = dict(
        con.execute(
            f"""
            select coalesce(list_position($bounds, list_filter($bounds, b -> b >= {column})[1]), $last), count(*)
            from {table} group by 1
            """,
            {"bounds": list(SIZE_BUCKETS), "last": len(SIZE_BUCKETS) + 1},
        ).fetchall()
    )
    return [(label, counts.get(n, 0)) for n, label in enumerate(labels, start=1)]


def match_counts(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str, int]]:
    return con.sql(f"select pass, {STRATUM_SQL} as stratum, count(*) from match group by all order by all").fetchall()  # type: ignore[return-value]


def cross_source_match_rate(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """How many Registrations reach a GLEIF record, firmly or possibly, and how many Carrier Entities hold one."""
    return dict(
        zip(
            ("registrations", "firm", "possible_only", "carriers", "carriers_with_gleif"),
            con.sql(
                """
                with fmcsa as (select record_id from source_record where source = 'FMCSA'),
                firm as (select distinct record_a as record_id from match where pass = 'B' and band = 'Firm'),
                possible as (select distinct record_a as record_id from match where pass = 'B' and band = 'Possible')
                select
                    (select count(*) from fmcsa),
                    (select count(*) from firm),
                    (select count(*) from possible anti join firm using (record_id)),
                    (select count(*) from entity where registrations > 0),
                    (select count(*) from entity where registrations > 0 and gleif_records > 0)
                """
            ).fetchall()[0],
            strict=True,
        )
    )


def flagged_entities(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, int, bool, bool]]:
    """Entities too large to trust, or holding more than one LEI: entity id, records, LEIs, and the two flags."""
    return con.sql(
        """
        select entity_id, records, gleif_records, oversized, several_leis
        from entity where oversized or several_leis
        order by records desc, entity_id
        """
    ).fetchall()  # type: ignore[return-value]


def sample_for_labelling(con: duckdb.DuckDBPyConnection, per_stratum: int, seed: int = 7) -> str:
    """A reproducible sample of Matches, `per_stratum` from each pass and stratum, as CSV text to label."""
    rows = con.execute(
        f"""
        with ranked as (
            select
                match.*,
                {STRATUM_SQL} as stratum,
                row_number() over (partition by pass, {STRATUM_SQL} order by hash(record_a || record_b, $seed))
                    as draw
            from match
        )
        select
            pass, stratum, record_a, record_b,
            a.name as name_a, a.street || ', ' || a.city || ', ' || a.state || ' ' || a.postal_code as address_a,
            b.name as name_b, b.street || ', ' || b.city || ', ' || b.state || ' ' || b.postal_code as address_b,
            evidence
        from ranked
        join source_record as a on a.record_id = ranked.record_a
        join source_record as b on b.record_id = ranked.record_b
        where draw <= $per_stratum
        order by pass, stratum, draw
        """,
        {"per_stratum": per_stratum, "seed": seed},
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([column[0] for column in rows.description or []] + ["same_entity", "note"])
    for row in rows.fetchall():
        writer.writerow([*row, "", ""])
    return buffer.getvalue()


def precision(con: duckdb.DuckDBPyConnection, labels_path: Path) -> list[tuple[str, str, int, int, int]]:
    """Per pass and stratum, as the rules stand now: pairs labelled same Entity, different, and unsure.

    A labelled pair that is no longer a Match is not counted; one whose stratum changed counts where it is now.
    """
    return con.execute(
        f"""
        select match.pass, {STRATUM_SQL.replace("band", "match.band")} as current_stratum,
            count(*) filter (where label.same_entity = 'yes'),
            count(*) filter (where label.same_entity = 'no'),
            count(*) filter (where label.same_entity not in ('yes', 'no')),
        from read_csv(?, header = true, all_varchar = true) as label
        join match using (record_a, record_b)
        group by all
        order by all
        """,
        [str(labels_path)],
    ).fetchall()  # type: ignore[return-value]


def labelled_pairs_no_longer_matched(con: duckdb.DuckDBPyConnection, labels_path: Path) -> list[tuple[str, str, int]]:
    """Labelled pairs the current rules no longer propose, by the pass and stratum they were drawn from."""
    return con.execute(
        """
        select label.pass, label.stratum, count(*)
        from read_csv(?, header = true, all_varchar = true) as label
        anti join match using (record_a, record_b)
        group by all
        order by all
        """,
        [str(labels_path)],
    ).fetchall()  # type: ignore[return-value]
