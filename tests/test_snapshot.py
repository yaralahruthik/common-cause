from pathlib import Path
from typing import Any

import duckdb
import pytest

from common_cause.ingest.build import BuildReport, build_snapshot
from common_cause.ingest.snapshot import load_snapshot

from .raw_sources import RawSourceBuilder


@pytest.fixture
def sources() -> RawSourceBuilder:
    return RawSourceBuilder()


def snapshot_of(sources: RawSourceBuilder, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    snapshot_dir = tmp_path / "snapshot"
    build_snapshot(sources.write(raw_dir), snapshot_dir)
    con = duckdb.connect()
    load_snapshot(con, snapshot_dir)
    return con


def column(con: duckdb.DuckDBPyConnection, sql: str) -> list[Any]:
    return [row[0] for row in con.sql(sql).fetchall()]


def test_keeps_records_with_a_us_legal_or_headquarters_address(sources, tmp_path):
    sources.lei_record("US_LEGAL", "Legal In US Inc", legal_country="US", hq_country="CA")
    sources.lei_record("US_HQ", "Head Office In US Ltd", legal_country="KY", hq_country="US")
    sources.lei_record("FOREIGN", "Nothing To Do With Us GmbH", legal_country="DE", hq_country="DE")

    con = snapshot_of(sources, tmp_path)

    assert sorted(column(con, "select lei from gleif_record")) == ["US_HQ", "US_LEGAL"]


def test_keeps_both_endpoints_of_a_consolidation_edge_wherever_they_are(sources, tmp_path):
    sources.lei_record("DE_CHILD", "Tochter GmbH", legal_country="DE", hq_country="DE")
    sources.lei_record("JP_PARENT", "Oya KK", legal_country="JP", hq_country="JP")
    sources.lei_record("LU_FUND", "Some Fund SICAV", legal_country="LU", hq_country="LU")
    sources.lei_record("LU_MANAGER", "Fund Manager SA", legal_country="LU", hq_country="LU")
    sources.relationship("DE_CHILD", "JP_PARENT", "IS_ULTIMATELY_CONSOLIDATED_BY")
    sources.relationship("LU_FUND", "LU_MANAGER", "IS_FUND-MANAGED_BY")

    con = snapshot_of(sources, tmp_path)

    assert sorted(column(con, "select lei from gleif_record")) == ["DE_CHILD", "JP_PARENT"]


def test_ownership_links_are_the_two_consolidation_types_only(sources, tmp_path):
    sources.lei_record("CHILD", "Child Inc")
    sources.lei_record("PARENT", "Parent Inc")
    sources.lei_record("TOP", "Top Holdings Inc")
    sources.relationship("CHILD", "PARENT", "IS_DIRECTLY_CONSOLIDATED_BY")
    sources.relationship("CHILD", "TOP", "IS_ULTIMATELY_CONSOLIDATED_BY", status="INACTIVE")
    sources.relationship("CHILD", "PARENT", "IS_FUND-MANAGED_BY")
    sources.relationship("CHILD", "TOP", "IS_INTERNATIONAL_BRANCH_OF")

    con = snapshot_of(sources, tmp_path)

    assert con.sql(
        "select child_lei, parent_lei, relationship_type, relationship_status from gleif_ownership_link order by all"
    ).fetchall() == [
        ("CHILD", "PARENT", "IS_DIRECTLY_CONSOLIDATED_BY", "ACTIVE"),
        ("CHILD", "TOP", "IS_ULTIMATELY_CONSOLIDATED_BY", "INACTIVE"),
    ]


def ownership_status(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    return dict(con.sql("select lei, ownership_status from gleif_ownership_status").fetchall())  # type: ignore[arg-type]


def test_an_active_consolidation_edge_is_a_declared_parent(sources, tmp_path):
    sources.lei_record("CHILD", "Child Inc")
    sources.lei_record("PARENT", "Parent Inc")
    sources.relationship("CHILD", "PARENT", "IS_DIRECTLY_CONSOLIDATED_BY")
    sources.exception("PARENT", "NATURAL_PERSONS")

    con = snapshot_of(sources, tmp_path)

    assert ownership_status(con) == {"CHILD": "Declared Parent", "PARENT": "Declared Independent"}


def test_natural_persons_and_non_consolidating_exceptions_are_declared_independent(sources, tmp_path):
    sources.lei_record("FAMILY", "Family Owned Inc")
    sources.lei_record("NONCONS", "Not Consolidated LLC")
    sources.exception("FAMILY", "NATURAL_PERSONS")
    sources.exception("NONCONS", "NON_CONSOLIDATING")

    con = snapshot_of(sources, tmp_path)

    assert ownership_status(con) == {"FAMILY": "Declared Independent", "NONCONS": "Declared Independent"}


def test_withheld_or_unfiled_ownership_is_an_undisclosed_parent(sources, tmp_path):
    sources.lei_record("NO_LEI", "Parent Has No LEI Inc")
    sources.lei_record("NON_PUBLIC", "Secretive Inc")
    sources.lei_record("NO_KNOWN", "Nobody Knows LLC")
    sources.lei_record("SILENT", "Never Filed Anything Inc")
    sources.lei_record("ENDED", "Used To Have A Parent Inc")
    sources.lei_record("OLD_PARENT", "Former Parent Inc")
    sources.exception("NO_LEI", "NO_LEI")
    sources.exception("NON_PUBLIC", "NON_PUBLIC")
    sources.exception("NO_KNOWN", "NO_KNOWN_PERSON")
    sources.relationship("ENDED", "OLD_PARENT", "IS_DIRECTLY_CONSOLIDATED_BY", status="INACTIVE")
    sources.exception("OLD_PARENT", "NATURAL_PERSONS")

    con = snapshot_of(sources, tmp_path)

    assert ownership_status(con) == {
        "NO_LEI": "Undisclosed Parent",
        "NON_PUBLIC": "Undisclosed Parent",
        "NO_KNOWN": "Undisclosed Parent",
        "SILENT": "Undisclosed Parent",
        "ENDED": "Undisclosed Parent",
        "OLD_PARENT": "Declared Independent",
    }


def test_an_exception_is_declared_independent_only_if_every_reason_says_so(sources, tmp_path):
    sources.lei_record("BOTH_INDEPENDENT", "Family And Unconsolidated Inc")
    sources.exception("BOTH_INDEPENDENT", "NATURAL_PERSONS", "NON_CONSOLIDATING")
    sources.lei_record("HEDGED", "Maybe Family Inc")
    sources.exception("HEDGED", "NATURAL_PERSONS", "NO_KNOWN_PERSON")

    con = snapshot_of(sources, tmp_path)

    assert ownership_status(con) == {"BOTH_INDEPENDENT": "Declared Independent", "HEDGED": "Undisclosed Parent"}


def test_the_direct_parent_exception_outranks_the_ultimate_one(sources, tmp_path):
    sources.lei_record("MIXED", "Mixed Signals Inc")
    sources.exception("MIXED", "NON_PUBLIC", category="ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT")
    sources.exception("MIXED", "NATURAL_PERSONS", category="DIRECT_ACCOUNTING_CONSOLIDATION_PARENT")
    sources.lei_record("ULTIMATE_ONLY", "Only Ultimate Filed Inc")
    sources.exception("ULTIMATE_ONLY", "NON_CONSOLIDATING", category="ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT")

    con = snapshot_of(sources, tmp_path)

    assert ownership_status(con) == {"MIXED": "Declared Independent", "ULTIMATE_ONLY": "Declared Independent"}


def test_reporting_exceptions_are_kept_only_for_records_in_the_slice(sources, tmp_path):
    sources.lei_record("US_CO", "American Inc")
    sources.lei_record("FR_CO", "Societe Francaise SA", legal_country="FR", hq_country="FR")
    sources.exception("US_CO", "NATURAL_PERSONS")
    sources.exception("FR_CO", "NATURAL_PERSONS")

    con = snapshot_of(sources, tmp_path)

    assert con.sql("select lei, exception_category, exception_reason_1 from gleif_reporting_exception").fetchall() == [
        ("US_CO", "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT", "NATURAL_PERSONS")
    ]


def test_census_keeps_registrations_with_ten_or_more_power_units_in_any_status(sources, tmp_path):
    sources.registration("100", "BIG FLEET INC", power_units="10", status_code="A")
    sources.registration("200", "LAPSED FLEET INC", power_units="250", status_code="I")
    sources.registration("300", "SMALL FLEET INC", power_units="9", status_code="A")
    sources.registration("400", "NO FLEET GIVEN INC", power_units="", status_code="A")

    con = snapshot_of(sources, tmp_path)

    assert con.sql("select dot_number, legal_name, status_code from fmcsa_census order by dot_number").fetchall() == [
        ("100", "BIG FLEET INC", "A"),
        ("200", "LAPSED FLEET INC", "I"),
    ]


def test_census_keeps_every_published_column(sources, tmp_path):
    sources.registration("100", "BIG FLEET INC", prior_revoke_dot_number="99", company_officer_1="JANE ROE")

    con = snapshot_of(sources, tmp_path)

    assert con.sql("select prior_revoke_dot_number, company_officer_1 from fmcsa_census").fetchall() == [
        ("99", "JANE ROE")
    ]


def test_out_of_service_orders_are_kept_only_for_registrations_in_the_census(sources, tmp_path):
    sources.registration("100", "BIG FLEET INC")
    sources.oos_order("100", "2024-01-05")
    sources.oos_order("100", "2025-03-02")
    sources.oos_order("555", "2024-06-01")

    con = snapshot_of(sources, tmp_path)

    assert con.sql("select dot_number, oos_date from fmcsa_oos_order order by oos_date").fetchall() == [
        ("100", "2024-01-05"),
        ("100", "2025-03-02"),
    ]


def test_every_table_carries_the_as_of_date_of_its_source(sources, tmp_path):
    sources.lei_record("CHILD", "Child Inc")
    sources.lei_record("PARENT", "Parent Inc")
    sources.relationship("CHILD", "PARENT", "IS_DIRECTLY_CONSOLIDATED_BY")
    sources.exception("PARENT", "NATURAL_PERSONS")
    sources.registration("100", "BIG FLEET INC")
    sources.oos_order("100", "2024-01-05")

    con = snapshot_of(sources, tmp_path)

    as_of = {
        table: column(con, f"select distinct cast(as_of_date as varchar) from {table}")
        for table in column(con, "select table_name from information_schema.tables order by 1")
    }
    assert as_of == {
        "fmcsa_census": ["2026-09-14"],
        "fmcsa_oos_order": ["2026-09-17"],
        "gleif_record": ["2026-09-18"],
        "gleif_ownership_link": ["2026-09-18"],
        "gleif_ownership_status": ["2026-09-18"],
        "gleif_reporting_exception": ["2026-09-18"],
    }


def build_report(sources: RawSourceBuilder, tmp_path: Path) -> BuildReport:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    return build_snapshot(sources.write(raw_dir), tmp_path / "snapshot")


def test_build_reports_row_counts_per_table(sources, tmp_path):
    sources.lei_record("CHILD", "Child Inc")
    sources.lei_record("PARENT", "Parent Inc")
    sources.relationship("CHILD", "PARENT", "IS_DIRECTLY_CONSOLIDATED_BY")
    sources.registration("100", "BIG FLEET INC")
    sources.registration("200", "OTHER FLEET INC")

    report = build_report(sources, tmp_path)

    assert report.table_rows == {
        "gleif_record": 2,
        "gleif_ownership_link": 1,
        "gleif_reporting_exception": 0,
        "gleif_ownership_status": 2,
        "fmcsa_census": 2,
        "fmcsa_oos_order": 0,
    }


def test_build_reports_every_relationship_type_in_the_full_file_including_skipped_ones(sources, tmp_path):
    sources.relationship("A", "B", "IS_DIRECTLY_CONSOLIDATED_BY")
    sources.relationship("A", "C", "IS_ULTIMATELY_CONSOLIDATED_BY")
    sources.relationship("D", "C", "IS_ULTIMATELY_CONSOLIDATED_BY")
    sources.relationship("F1", "M", "IS_FUND-MANAGED_BY")
    sources.relationship("F2", "M", "IS_FUND-MANAGED_BY")
    sources.relationship("F1", "U", "IS_SUBFUND_OF")

    report = build_report(sources, tmp_path)

    assert report.relationship_types == {
        "IS_DIRECTLY_CONSOLIDATED_BY": 1,
        "IS_ULTIMATELY_CONSOLIDATED_BY": 2,
        "IS_FUND-MANAGED_BY": 2,
        "IS_SUBFUND_OF": 1,
    }


def test_a_rebuild_leaves_no_table_from_an_earlier_snapshot(sources, tmp_path):
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    duckdb.sql("select 1 as retired").write_parquet(str(snapshot_dir / "retired_table.parquet"))

    con = snapshot_of(sources, tmp_path)

    assert "retired_table" not in column(con, "select table_name from information_schema.tables")
