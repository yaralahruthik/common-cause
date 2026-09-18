from pathlib import Path

import pytest

from common_cause.exposure.graph import Graph, Member

from .raw_sources import RawSourceBuilder
from .snapshots import built_snapshot

DIRECT = "IS_DIRECTLY_CONSOLIDATED_BY"
ULTIMATE = "IS_ULTIMATELY_CONSOLIDATED_BY"


@pytest.fixture
def sources() -> RawSourceBuilder:
    return RawSourceBuilder()


def opened(sources: RawSourceBuilder, tmp_path: Path) -> Graph:
    return Graph.open(built_snapshot(sources, tmp_path), tmp_path / "state.duckdb")


def gleif(sources: RawSourceBuilder, lei: str, name: str, *, street: str = "", zip5: str = "", **extra: str) -> None:
    sources.lei_record(
        lei,
        name,
        **{
            "Entity.HeadquartersAddress.FirstAddressLine": street or f"{lei} Commerce Drive",
            "Entity.HeadquartersAddress.City": "Chicago",
            "Entity.HeadquartersAddress.Region": "US-IL",
            "Entity.HeadquartersAddress.PostalCode": zip5 or "60601",
            **extra,
        },
    )


def matched(graph: Graph, portfolio_id: str) -> list[list[tuple[str, str]]]:
    """Each member's Matches as (entity id, band)."""
    return [[(m.entity_id, m.band) for m in member.matches] for member in graph.portfolio(portfolio_id)]


def concentrations(graph: Graph, portfolio_id: str) -> list[tuple[str, str, list[int], bool]]:
    """Each Hidden Concentration as (Common Cause kind, label, member ids, tentative), in ranked order."""
    return [
        (c.kind, c.label, [m.member_id for m in c.members], c.tentative)
        for c in graph.exposure(portfolio_id).concentrations
    ]


# Portfolio intake


def test_a_name_with_one_exact_normalised_hit_is_a_firm_match(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.")
    gleif(sources, "LEI2", "Acme Food Service LLC")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("the acme foods company")])

    assert matched(graph, portfolio_id) == [[("gleif:LEI1", "Firm")]]
    assert graph.portfolio(portfolio_id)[0].matches[0].name == "Acme Foods, Inc."


def test_a_name_held_by_several_entities_gives_possible_matches(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.")
    sources.registration("100", "ACME FOODS LLC", phy_street="9 ELM ST", phy_zip="73301", phy_state="TX")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods")])

    assert matched(graph, portfolio_id) == [[("fmcsa:100", "Possible"), ("gleif:LEI1", "Possible")]]


def test_a_state_narrows_several_exact_hits_to_one_firm_match(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.")
    sources.registration("100", "ACME FOODS LLC", phy_street="9 ELM ST", phy_zip="73301", phy_state="TX")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods", state="tx")])

    assert matched(graph, portfolio_id) == [[("fmcsa:100", "Firm")]]


def test_a_city_narrows_several_exact_hits_to_one_firm_match(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.")
    sources.registration("100", "ACME FOODS LLC", phy_city="SPRINGFIELD", phy_state="IL", phy_zip="62701")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods", state="IL", city="Chicago")])

    assert matched(graph, portfolio_id) == [[("gleif:LEI1", "Firm")]]


def test_a_near_name_is_a_possible_match_and_at_most_three_are_offered(sources, tmp_path):
    for n, name in enumerate(["Acme Freight Lines", "Acme Freight Line", "Acme Freight", "Acme Frieght Lines"]):
        gleif(sources, f"LEI{n}", name)
    gleif(sources, "LEI4", "Acme Freight Liner")
    gleif(sources, "LEI9", "Zenith Freight Lines")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Freihgt Lines")])

    assert [(m.entity_id, m.band, m.score) for m in graph.portfolio(portfolio_id)[0].matches] == [
        ("gleif:LEI0", "Possible", 0.99),
        ("gleif:LEI1", "Possible", 0.977),
        ("gleif:LEI3", "Possible", 0.975),
    ]


def test_a_firm_match_keeps_the_near_names_so_rejecting_it_leaves_something_to_confirm(sources, tmp_path):
    gleif(sources, "LEI0", "Acme Freight Lines")
    gleif(sources, "LEI1", "Acme Freight Line")
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Freight Lines")])

    assert matched(graph, portfolio_id) == [[("gleif:LEI0", "Firm"), ("gleif:LEI1", "Possible")]]
    graph.record_verdict(portfolio_id, 1, "gleif:LEI0", "rejected")
    graph.record_verdict(portfolio_id, 1, "gleif:LEI1", "confirmed")

    assert [(m.entity_id, m.verdict) for m in graph.portfolio(portfolio_id)[0].matches] == [
        ("gleif:LEI0", "rejected"),
        ("gleif:LEI1", "confirmed"),
    ]


def test_a_name_that_normalises_to_nothing_or_matches_nothing_has_no_match(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Inc."), Member("Zenith Hauling")])

    assert matched(graph, portfolio_id) == [[], []]


def test_a_trade_name_matches_the_entity_that_holds_it(sources, tmp_path):
    sources.registration("100", "SMITH HOLDINGS LLC", dba_name="ACME FOODS", phy_zip="60601", phy_state="IL")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods")])

    assert matched(graph, portfolio_id) == [[("fmcsa:100", "Firm")]]


# Hidden Concentrations


def test_members_under_one_ultimate_parent_several_hops_up_are_a_concentration(sources, tmp_path):
    gleif(sources, "PLANT", "Acme Plant Co")
    gleif(sources, "SUB", "Acme Regional LLC")
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "BRAND", "Brandco Foods LLC")
    gleif(sources, "ALONE", "Zenith Foods Inc")
    sources.relationship("PLANT", "SUB", DIRECT)
    sources.relationship("SUB", "HOLD", DIRECT)
    sources.relationship("BRAND", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Plant"), Member("Brandco Foods"), Member("Zenith Foods")])

    exposure = graph.exposure(portfolio_id)
    assert [(c.kind, c.label, c.share) for c in exposure.concentrations] == [
        ("Ultimate Parent", "Acme Holdings Inc", 2 / 3)
    ]
    assert [[step.lei for step in m.path] for m in exposure.concentrations[0].members] == [
        ["PLANT", "SUB", "HOLD"],
        ["BRAND", "HOLD"],
    ]


def test_a_member_that_is_the_parent_of_another_shares_its_ultimate_parent(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    sources.relationship("SUB", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])

    assert ("Ultimate Parent", "Acme Holdings Inc", [1, 2], False) in concentrations(graph, portfolio_id)


def test_the_declared_ultimate_parent_stands_in_where_the_chain_breaks(sources, tmp_path):
    gleif(sources, "A", "Acme Foods Inc")
    gleif(sources, "B", "Brandco Foods LLC")
    sources.relationship("A", "B", DIRECT)
    sources.relationship("B", "A", DIRECT)
    sources.relationship("A", "TOP", ULTIMATE)
    sources.relationship("B", "TOP", ULTIMATE)
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods"), Member("Brandco Foods")])

    assert concentrations(graph, portfolio_id) == [("Ultimate Parent", "LEI TOP", [1, 2], False)]


def test_members_at_one_physical_address_are_a_concentration(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods Inc", street="4500 W 47th Street", zip5="60632")
    sources.registration("100", "ZENITH HAULING LLC", phy_street="4500 W 47TH ST", phy_zip="60632-1234", phy_state="IL")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods"), Member("Zenith Hauling")])

    assert concentrations(graph, portfolio_id) == [("Address", "4500 W 47TH ST, 60632", [1, 2], False)]


def test_an_agent_address_is_not_a_common_cause(sources, tmp_path):
    for n in range(11):
        gleif(
            sources, f"TENANT{n:02}", f"Tenant Number {n} Holdings LLC", street="251 Little Falls Drive", zip5="19808"
        )
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Tenant Number 1 Holdings"), Member("Tenant Number 2 Holdings")])

    assert concentrations(graph, portfolio_id) == []


def test_members_in_one_jurisdiction_are_a_concentration(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods Inc", **{"Entity.LegalJurisdiction": "US-DE"})
    gleif(sources, "LEI2", "Zenith Foods Inc", **{"Entity.LegalJurisdiction": "US-DE"})
    gleif(sources, "LEI3", "Brandco Foods Inc", **{"Entity.LegalJurisdiction": "US-IL"})
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods"), Member("Zenith Foods"), Member("Brandco Foods")])

    assert concentrations(graph, portfolio_id) == [("Jurisdiction", "US-DE", [1, 2], False)]


def test_concentrations_are_ranked_by_share_of_the_portfolio(sources, tmp_path):
    for lei, name in [("A", "Acme Foods"), ("B", "Brandco Foods"), ("C", "Crate Foods"), ("D", "Delta Foods")]:
        gleif(sources, lei, f"{name} Inc")
    gleif(sources, "E", "Echo Foods Inc")
    sources.relationship("B", "A", DIRECT)
    sources.relationship("C", "A", DIRECT)
    sources.relationship("E", "D", DIRECT)
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio(
        [
            Member("Delta Foods"),
            Member("Echo Foods"),
            Member("Acme Foods"),
            Member("Brandco Foods"),
            Member("Crate Foods"),
        ]
    )

    assert [(c.label, c.share) for c in graph.exposure(portfolio_id).concentrations] == [
        ("Acme Foods Inc", 3 / 5),
        ("Delta Foods Inc", 2 / 5),
    ]


def test_a_shared_jurisdiction_ranks_after_ownership_and_address_however_large(sources, tmp_path):
    for lei, name in [("A", "Acme Foods Inc"), ("B", "Brandco Foods Inc"), ("C", "Zenith Foods Inc")]:
        gleif(sources, lei, name, **{"Entity.LegalJurisdiction": "US-DE"})
    sources.relationship("B", "A", DIRECT)
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods"), Member("Brandco Foods"), Member("Zenith Foods")])

    assert concentrations(graph, portfolio_id) == [
        ("Ultimate Parent", "Acme Foods Inc", [1, 2], False),
        ("Jurisdiction", "US-DE", [1, 2, 3], False),
    ]


def test_two_members_matched_to_one_entity_are_not_a_concentration(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods Inc", **{"Entity.LegalJurisdiction": "US-DE"})
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods"), Member("The Acme Foods Company")])

    assert concentrations(graph, portfolio_id) == []


def test_the_share_counts_members_matched_firmly_and_says_what_it_would_be_if_possible_matches_hold(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    gleif(sources, "CRATE1", "Crate Foods LLC")
    gleif(sources, "CRATE2", "Crate Foods Inc")
    sources.relationship("SUB", "HOLD", DIRECT)
    sources.relationship("CRATE1", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods"), Member("Crate Foods")])

    [concentration] = graph.exposure(portfolio_id).concentrations
    assert (concentration.share, concentration.share_if_possible_matches_hold, concentration.tentative) == (
        2 / 3,
        1.0,
        False,
    )
    assert [(m.member_id, m.firm) for m in concentration.members] == [(1, True), (2, True), (3, False)]


def test_a_concentration_that_depends_on_a_possible_match_is_tentative(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    gleif(sources, "OTHER", "Brandco Foods Inc", street="1 Other Road", zip5="10001")
    sources.relationship("SUB", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])

    assert concentrations(graph, portfolio_id) == [("Ultimate Parent", "Acme Holdings Inc", [1, 2], True)]


def test_confirming_the_possible_match_makes_the_concentration_firm(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    gleif(sources, "OTHER", "Brandco Foods Inc", street="1 Other Road", zip5="10001")
    sources.relationship("SUB", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])

    graph.record_verdict(portfolio_id, 2, "gleif:SUB", "confirmed")

    assert concentrations(graph, portfolio_id) == [("Ultimate Parent", "Acme Holdings Inc", [1, 2], False)]
    assert [(m.entity_id, m.verdict) for m in graph.portfolio(portfolio_id)[1].matches] == [
        ("gleif:OTHER", None),
        ("gleif:SUB", "confirmed"),
    ]


def test_rejecting_a_match_removes_its_concentration(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    sources.relationship("SUB", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])

    graph.record_verdict(portfolio_id, 2, "gleif:SUB", "rejected")

    assert concentrations(graph, portfolio_id) == []


def test_a_verdict_holds_for_its_own_portfolio_only_and_survives_a_restart(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    sources.relationship("SUB", "HOLD", DIRECT)
    snapshot_dir = built_snapshot(sources, tmp_path)
    graph = Graph.open(snapshot_dir, tmp_path / "state.duckdb")
    members = [Member("Acme Holdings"), Member("Brandco Foods")]
    rejected, untouched = graph.create_portfolio(members), graph.create_portfolio(members)
    graph.record_verdict(rejected, 2, "gleif:SUB", "rejected")
    graph.close()

    graph = Graph.open(snapshot_dir, tmp_path / "state.duckdb")

    assert concentrations(graph, rejected) == []
    assert len(concentrations(graph, untouched)) == 1


def test_a_verdict_survives_a_rebuild_that_changes_the_entity_it_was_given_on(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods Inc")
    before = built_snapshot(sources, tmp_path / "before")
    sources.registration("100", "ACME FOODS INC", phy_street="9 Yard Road", phy_zip="60601", phy_state="IL")
    after = built_snapshot(sources, tmp_path / "after")
    graph = Graph.open(before, tmp_path / "state.duckdb")
    portfolio_id = graph.create_portfolio([Member("Acme Foods")])
    graph.record_verdict(portfolio_id, 1, "gleif:LEI1", "rejected")
    graph.close()

    graph = Graph.open(after, tmp_path / "state.duckdb")

    assert [(m.entity_id, m.verdict) for m in graph.portfolio(portfolio_id)[0].matches] == [("fmcsa:100", "rejected")]


def test_a_verdict_on_an_entity_the_member_was_not_matched_to_is_refused(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods Inc")
    gleif(sources, "LEI2", "Zenith Foods Inc")
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Foods")])

    with pytest.raises(LookupError):
        graph.record_verdict(portfolio_id, 1, "gleif:LEI2", "confirmed")
    with pytest.raises(LookupError):
        graph.record_verdict(portfolio_id, 2, "gleif:LEI1", "confirmed")
    with pytest.raises(LookupError):
        graph.exposure("no-such-portfolio")


# Ownership Status


def test_unverifiable_ownership_counts_undisclosed_parents_and_members_not_matched_apart(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    gleif(sources, "OWNED", "Owned By People Inc")
    gleif(sources, "SECRET", "Secretive Foods Inc")
    sources.relationship("SUB", "HOLD", DIRECT)
    sources.exception("HOLD", "NATURAL_PERSONS")
    sources.exception("OWNED", "NATURAL_PERSONS")
    sources.exception("SECRET", "NON_PUBLIC")
    sources.registration("100", "ZENITH HAULING LLC", phy_zip="73301", phy_state="TX")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio(
        [
            Member("Brandco Foods"),
            Member("Owned By People"),
            Member("Secretive Foods"),
            Member("Zenith Hauling"),
            Member("Nobody Known"),
        ]
    )

    ownership = graph.exposure(portfolio_id).ownership
    assert [(m.member_id, m.status, m.basis) for m in ownership.members] == [
        (1, "Declared Parent", "IS_DIRECTLY_CONSOLIDATED_BY"),
        (2, "Declared Independent", "exception: NATURAL_PERSONS"),
        (3, "Undisclosed Parent", "exception: NON_PUBLIC"),
        (4, "Undisclosed Parent", "no GLEIF record"),
        (5, None, "no Firm Match"),
    ]
    assert (ownership.unverifiable, ownership.matched, ownership.unmatched, ownership.total) == (2, 4, 1, 5)


def test_a_member_whose_walked_and_declared_ultimate_parents_disagree_is_counted(sources, tmp_path):
    gleif(sources, "A", "Acme Foods Inc")
    gleif(sources, "B", "Brandco Foods Inc")
    sources.relationship("A", "B", DIRECT)
    sources.relationship("A", "ELSEWHERE", ULTIMATE)
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods"), Member("Brandco Foods")])

    disagreements = graph.exposure(portfolio_id).ownership.disagreements
    assert [(d.member_id, d.walked_lei, d.declared_lei) for d in disagreements] == [(1, "B", "ELSEWHERE")]


def test_members_affected_counts_firm_members_of_firm_concentrations_other_than_jurisdiction(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    sources.relationship("SUB", "HOLD", DIRECT)
    gleif(sources, "PEP", "Pepco Foods Inc")
    gleif(sources, "XYLO1", "Xylo Juice LLC")
    gleif(sources, "XYLO2", "Xylo Juice Inc", street="1 Other Road", zip5="10001")
    sources.relationship("XYLO1", "PEP", DIRECT)
    gleif(sources, "D", "Delta Foods Inc", **{"Entity.LegalJurisdiction": "US-DE"})
    gleif(sources, "E", "Echo Foods Inc", **{"Entity.LegalJurisdiction": "US-DE"})
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio(
        [Member(name) for name in ["Acme Holdings", "Brandco Foods", "Pepco Foods", "Xylo Juice", "Delta", "Echo"]]
    )

    exposure = graph.exposure(portfolio_id)
    # Pepco Foods is matched firmly, but its only concentration rests on Xylo Juice, which is not.
    assert (exposure.affected, exposure.affected_if_possible_matches_hold) == (2, 4)


def test_a_concentration_has_an_id_that_survives_a_restart(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    sources.relationship("SUB", "HOLD", DIRECT)
    snapshot_dir = built_snapshot(sources, tmp_path)
    graph = Graph.open(snapshot_dir, tmp_path / "state.duckdb")
    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])
    [before] = graph.exposure(portfolio_id).concentrations
    graph.close()

    [after] = Graph.open(snapshot_dir, tmp_path / "state.duckdb").exposure(portfolio_id).concentrations

    assert before.id == after.id
    assert before.id.isalnum()


def test_a_match_lists_every_record_of_the_entity_it_points_to(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods Inc", street="9 Yard Road", zip5="60601")
    sources.registration("100", "ACME FOODS INC", phy_street="9 YARD ROAD", phy_zip="60601", phy_state="IL")
    graph = opened(sources, tmp_path)

    portfolio_id = graph.create_portfolio([Member("Acme Foods")])

    [match] = graph.portfolio(portfolio_id)[0].matches
    assert match.entity_records == ["fmcsa:100", "gleif:LEI1"]


def test_clearing_a_verdict_restores_the_match_as_it_was(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    sources.relationship("SUB", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])
    graph.record_verdict(portfolio_id, 2, "gleif:SUB", "rejected")

    graph.clear_verdict(portfolio_id, 2, "gleif:SUB")

    assert [(m.entity_id, m.verdict) for m in graph.portfolio(portfolio_id)[1].matches] == [("gleif:SUB", None)]
    assert len(graph.exposure(portfolio_id).concentrations) == 1
    with pytest.raises(LookupError):
        graph.clear_verdict(portfolio_id, 2, "gleif:HOLD")


def test_a_member_can_be_searched_again_under_another_name(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods Inc")
    sources.registration("100", "ACME FOODS LLC", phy_street="9 ELM ST", phy_zip="73301", phy_state="TX")
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Zenith Hauling")])
    assert matched(graph, portfolio_id) == [[]]

    graph.update_member(portfolio_id, 1, Member("Acme Foods", state="TX"))

    [member] = graph.portfolio(portfolio_id)
    assert (member.name, member.state, [(m.entity_id, m.band) for m in member.matches]) == (
        "Acme Foods",
        "TX",
        [("fmcsa:100", "Firm")],
    )
    with pytest.raises(LookupError):
        graph.update_member(portfolio_id, 2, Member("Acme Foods"))
