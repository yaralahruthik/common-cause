"""`make resolve`: resolve the snapshot into Entities and report the scale and quality signals."""

import argparse
import time
from pathlib import Path

import duckdb

from common_cause.exposure.ownership import MAX_CHAIN_HOPS, build_ownership, chain_summary
from common_cause.ingest.snapshot import DEFAULT_SNAPSHOT_DIR, load_snapshot
from common_cause.resolve import report
from common_cause.resolve.resolution import MAX_BLOCK_RECORDS, OVERSIZED_ENTITY_RECORDS, resolve


def _histogram(title: str, rows: list[tuple[str, int]]) -> None:
    print(f"\n| {title} | Count |")
    print("|---|---:|")
    for bucket, count in rows:
        print(f"| {bucket} | {count:,} |")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m common_cause.resolve", description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--labels", type=Path, default=report.DEFAULT_LABELS_PATH)
    parser.add_argument(
        "--sample-labels",
        type=int,
        metavar="N",
        help="write N unlabelled Matches per pass and stratum to --labels instead of reporting; refuses to overwrite",
    )
    args = parser.parse_args()

    con = duckdb.connect()
    con.execute("set enable_progress_bar = false")
    load_snapshot(con, args.snapshot_dir)
    started = time.perf_counter()
    resolve(con)
    print(f"Resolved in {time.perf_counter() - started:.0f}s")

    if args.sample_labels:
        if args.labels.exists():
            raise SystemExit(f"{args.labels} exists; labels are hand-made, move it aside first")
        args.labels.parent.mkdir(parents=True, exist_ok=True)
        args.labels.write_text(report.sample_for_labelling(con, args.sample_labels))
        print(f"Wrote a sample to label to {args.labels}")
        return

    print("\n| Pass | Band | Matches |")
    print("|---|---|---:|")
    for pass_, stratum, count in report.match_counts(con):
        print(f"| {pass_} | {stratum} | {count:,} |")

    rate = report.cross_source_match_rate(con)
    print(
        f"\nCross-source: {rate['firm']:,} of {rate['registrations']:,} Registrations "
        f"({rate['firm'] / rate['registrations']:.1%}) have a Firm Match to a GLEIF record; "
        f"{rate['possible_only']:,} more ({rate['possible_only'] / rate['registrations']:.1%}) only a Possible one. "
        f"{rate['carriers_with_gleif']:,} of {rate['carriers']:,} Carrier Entities "
        f"({rate['carriers_with_gleif'] / rate['carriers']:.1%}) include a GLEIF record."
    )

    _histogram("Records per blocking key", report.size_histogram(con, "block_size", "records"))
    skipped = con.execute(
        "select block_key, records from block_size where records > ? order by records desc", [MAX_BLOCK_RECORDS]
    ).fetchall()
    print(f"\nBlocks over {MAX_BLOCK_RECORDS} records skipped: {len(skipped)}")
    for block_key, records in skipped:
        print(f"  {block_key}: {records:,}")
    _histogram("Source Records per Entity", report.size_histogram(con, "entity", "records"))
    flagged = report.flagged_entities(con)
    print(f"\nEntities over {OVERSIZED_ENTITY_RECORDS} records: {sum(row[3] for row in flagged)}")
    print(f"Entities holding more than one LEI: {sum(row[4] for row in flagged)}")
    for entity_id, records, leis, _, _ in flagged:
        print(f"  {entity_id}: {records} records, {leis} LEIs")

    build_ownership(con)
    print(f"\n| Ultimate Parent found by | Chain break (cap {MAX_CHAIN_HOPS} hops) | GLEIF records | Disagreements |")
    print("|---|---|---:|---:|")
    for basis, chain_break, records, disagreements in chain_summary(con):
        print(f"| {basis} | {chain_break} | {records:,} | {disagreements:,} |")

    if args.labels.exists():
        print("\n| Pass | Band | Same Entity | Different | Unsure | Precision |")
        print("|---|---|---:|---:|---:|---:|")
        for pass_, stratum, same, different, unsure in report.precision(con, args.labels):
            measured = f"{same / (same + different):.0%}" if same + different else "n/a"
            print(f"| {pass_} | {stratum} | {same} | {different} | {unsure} | {measured} |")
        for pass_, stratum, count in report.labelled_pairs_no_longer_matched(con, args.labels):
            print(f"\n{count} labelled pairs drawn from pass {pass_}, {stratum}, are no longer Matches.")


if __name__ == "__main__":
    main()
