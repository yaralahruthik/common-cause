import duckdb
import pytest

from common_cause.exposure.ownership import MAX_CHAIN_HOPS, build_ownership

from .raw_sources import RawSourceBuilder
from .snapshots import loaded

DIRECT = "IS_DIRECTLY_CONSOLIDATED_BY"
ULTIMATE = "IS_ULTIMATELY_CONSOLIDATED_BY"


@pytest.fixture
def sources() -> RawSourceBuilder:
    return RawSourceBuilder()


def ownership(sources: RawSourceBuilder, tmp_path) -> duckdb.DuckDBPyConnection:
    con = loaded(sources, tmp_path)
    build_ownership(con)
    return con


def ultimate_parent(con: duckdb.DuckDBPyConnection, lei: str) -> tuple:
    """(Ultimate Parent, basis, where the chain broke, walked path) for one LEI."""
    return con.execute(
        "select ultimate_parent_lei, basis, chain_break, path from ultimate_parent where lei = ?", [lei]
    ).fetchone()  # type: ignore[return-value]


def companies(sources: RawSourceBuilder, *leis: str) -> None:
    for lei in leis:
        sources.lei_record(lei, f"Company {lei}")


def test_a_company_with_no_parent_is_its_own_ultimate_parent(sources, tmp_path):
    companies(sources, "A")

    con = ownership(sources, tmp_path)

    assert ultimate_parent(con, "A") == ("A", "walked", None, ["A"])


def test_the_ultimate_parent_is_reached_by_walking_direct_links_over_several_hops(sources, tmp_path):
    companies(sources, "PLANT", "SUB", "HOLDCO", "TOP")
    sources.relationship("PLANT", "SUB", DIRECT)
    sources.relationship("SUB", "HOLDCO", DIRECT)
    sources.relationship("HOLDCO", "TOP", DIRECT)
    sources.relationship("PLANT", "TOP", ULTIMATE)

    con = ownership(sources, tmp_path)

    assert ultimate_parent(con, "PLANT") == ("TOP", "walked", None, ["PLANT", "SUB", "HOLDCO", "TOP"])
    assert ultimate_parent(con, "HOLDCO") == ("TOP", "walked", None, ["HOLDCO", "TOP"])


def test_an_inactive_link_is_not_walked(sources, tmp_path):
    companies(sources, "A", "B")
    sources.relationship("A", "B", DIRECT, status="INACTIVE")

    con = ownership(sources, tmp_path)

    assert ultimate_parent(con, "A") == ("A", "walked", None, ["A"])


def test_a_parent_missing_from_the_registry_can_still_be_the_ultimate_parent(sources, tmp_path):
    companies(sources, "A")
    sources.relationship("A", "UNLISTED", DIRECT)

    con = ownership(sources, tmp_path)

    assert ultimate_parent(con, "A") == ("UNLISTED", "walked", None, ["A", "UNLISTED"])


def test_a_cycle_falls_back_to_the_declared_ultimate_parent(sources, tmp_path):
    companies(sources, "A", "B", "C", "TOP")
    sources.relationship("A", "B", DIRECT)
    sources.relationship("B", "C", DIRECT)
    sources.relationship("C", "B", DIRECT)
    sources.relationship("A", "TOP", ULTIMATE)

    con = ownership(sources, tmp_path)

    assert ultimate_parent(con, "A") == ("TOP", "declared", "cycle", ["A", "B", "C", "B"])


def test_every_company_in_an_undeclared_cycle_shares_one_ultimate_parent(sources, tmp_path):
    companies(sources, "A", "B", "C")
    sources.relationship("A", "B", DIRECT)
    sources.relationship("B", "C", DIRECT)
    sources.relationship("C", "B", DIRECT)

    con = ownership(sources, tmp_path)

    assert [ultimate_parent(con, lei)[:3] for lei in ("A", "B", "C")] == [("B", "partial walk", "cycle")] * 3


def test_a_chain_whose_top_declares_a_parent_it_has_no_link_to_is_broken(sources, tmp_path):
    companies(sources, "A", "B", "TOP")
    sources.relationship("A", "B", DIRECT)
    sources.relationship("B", "TOP", ULTIMATE)

    con = ownership(sources, tmp_path)

    assert ultimate_parent(con, "A") == ("TOP", "declared", "missing direct link", ["A", "B"])


def test_a_chain_longer_than_the_depth_cap_falls_back_to_the_declared_ultimate_parent(sources, tmp_path):
    chain = [f"L{n:02}" for n in range(MAX_CHAIN_HOPS + 2)]
    companies(sources, *chain)
    for child, parent in zip(chain, chain[1:], strict=False):
        sources.relationship(child, parent, DIRECT)
    sources.relationship("L00", chain[-1], ULTIMATE)

    con = ownership(sources, tmp_path)

    assert ultimate_parent(con, "L00")[:3] == (chain[-1], "declared", "depth cap")
    assert ultimate_parent(con, "L01")[:3] == (chain[-1], "walked", None)


def test_a_declared_ultimate_parent_that_disagrees_with_the_walk_is_counted_and_the_walk_wins(sources, tmp_path):
    companies(sources, "A", "B", "TOP", "OTHER", "C")
    sources.relationship("A", "B", DIRECT)
    sources.relationship("B", "TOP", DIRECT)
    sources.relationship("A", "OTHER", ULTIMATE)
    sources.relationship("C", "TOP", DIRECT)
    sources.relationship("C", "TOP", ULTIMATE)

    con = ownership(sources, tmp_path)

    assert ultimate_parent(con, "A")[:2] == ("TOP", "walked")
    assert con.sql(
        "select lei, declared_ultimate_parent_lei from ultimate_parent where disagrees order by lei"
    ).fetchall() == [("A", "OTHER")]
