from datetime import date
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


def only_concentration_id(graph: Graph, portfolio_id: str) -> str:
    [concentration] = [c for c in graph.exposure(portfolio_id).concentrations if c.kind != "Jurisdiction"]
    return concentration.id


def test_a_shared_parent_is_shown_as_each_members_path_with_the_jurisdiction_of_every_hop(sources, tmp_path):
    gleif(sources, "PLANT", "Acme Plant Co", **{"Entity.LegalJurisdiction": "US-MO"})
    gleif(sources, "SUB", "Acme Regional LLC", **{"Entity.LegalJurisdiction": "US-DE"})
    sources.lei_record(
        "HOLD", "Acme Holding S.A.", legal_country="CH", hq_country="CH", **{"Entity.LegalJurisdiction": "CH"}
    )
    gleif(sources, "BRAND", "Brandco Foods LLC")
    for child, parent in [("PLANT", "SUB"), ("SUB", "HOLD"), ("BRAND", "HOLD")]:
        sources.relationship(child, parent, DIRECT)
        sources.relationship(child, "HOLD", ULTIMATE)
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Plant"), Member("Brandco Foods")])

    detail = graph.concentration(portfolio_id, only_concentration_id(graph, portfolio_id))

    assert (detail.kind, detail.label, detail.tentative, detail.rank, detail.ranked) == (
        "Ultimate Parent",
        "Acme Holding S.A.",
        False,
        1,
        1,
    )
    plant, brand = detail.members
    assert [(s.lei, s.name, s.jurisdiction) for s in plant.path] == [
        ("PLANT", "Acme Plant Co", "US-MO"),
        ("SUB", "Acme Regional LLC", "US-DE"),
        ("HOLD", "Acme Holding S.A.", "CH"),
    ]
    assert (plant.basis, plant.declared_ultimate_parent_lei, brand.declared_ultimate_parent_lei) == (
        "walked",
        "HOLD",
        "HOLD",
    )
    assert (plant.ownership_status, plant.leis, plant.registrations) == ("Declared Parent", ["PLANT"], [])
    assert detail.as_of["GLEIF"] == date(2026, 9, 18)


def test_where_the_chain_breaks_the_path_ends_at_the_declared_ultimate_parent(sources, tmp_path):
    gleif(sources, "A", "Acme Foods Inc")
    gleif(sources, "B", "Brandco Foods LLC")
    gleif(sources, "TOP", "Topco Holdings Inc")
    sources.relationship("A", "B", DIRECT)
    sources.relationship("B", "A", DIRECT)
    sources.relationship("A", "TOP", ULTIMATE)
    sources.relationship("B", "TOP", ULTIMATE)
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Foods"), Member("Brandco Foods")])

    detail = graph.concentration(portfolio_id, only_concentration_id(graph, portfolio_id))

    acme = detail.members[0]
    assert ([s.lei for s in acme.path], acme.basis) == (["A", "B", "TOP"], "declared")


def test_each_members_registrations_carry_status_fleet_filing_date_and_out_of_service_orders(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC", street="9 Yard Road", zip5="60601")
    sources.relationship("SUB", "HOLD", DIRECT)
    sources.registration(
        "100",
        "BRANDCO FOODS LLC",
        power_units="27",
        status_code="A",
        mcs150_date="20250916",
        phy_street="9 YARD ROAD",
        phy_city="CHICAGO",
        phy_state="IL",
        phy_zip="60601",
    )
    sources.registration(
        "200",
        "BRANDCO FOODS LLC",
        power_units="11",
        status_code="I",
        dba_name="TEJAS INDUSTRIES",
        mcs150_date="20240220",
        phy_street="9 YARD ROAD",
        phy_city="CHICAGO",
        phy_state="IL",
        phy_zip="60601",
    )
    sources.oos_order("200", "2016-10-30", rescind_date="2016-11-30")
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])

    detail = graph.concentration(portfolio_id, only_concentration_id(graph, portfolio_id))

    holdings, brandco = detail.members
    assert holdings.registrations == []
    assert [
        (r.dot_number, r.name, r.dba_name, r.status, r.power_units, r.street, r.city, r.state, r.zip, r.last_filed)
        for r in brandco.registrations
    ] == [
        ("100", "BRANDCO FOODS LLC", None, "Active", 27, "9 YARD ROAD", "CHICAGO", "IL", "60601", date(2025, 9, 16)),
        (
            "200",
            "BRANDCO FOODS LLC",
            "TEJAS INDUSTRIES",
            "Inactive",
            11,
            "9 YARD ROAD",
            "CHICAGO",
            "IL",
            "60601",
            date(2024, 2, 20),
        ),
    ]
    assert brandco.registrations[0].out_of_service == []
    [order] = brandco.registrations[1].out_of_service
    assert (order.ordered, order.reason, order.status, order.rescinded) == (
        date(2016, 10, 30),
        "Unsatisfactory = Unfit",
        "ACTIVE",
        date(2016, 11, 30),
    )


def test_a_shared_address_names_the_site_and_everyone_else_registered_there(sources, tmp_path):
    for dot, name in [("100", "PRAIRIE DAIRY"), ("200", "EAST SIDE DAIRY"), ("300", "ICE CREAM MAKERS INC")]:
        sources.registration(
            dot, name, phy_street="3744 STAUNTON ROAD", phy_city="EDWARDSVILLE", phy_state="IL", phy_zip="62025"
        )
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Prairie Dairy"), Member("East Side Dairy")])

    detail = graph.concentration(portfolio_id, only_concentration_id(graph, portfolio_id))

    assert detail.kind == "Address"
    assert detail.site is not None
    site = detail.site
    assert (site.street, site.city, site.state, site.zip) == ("3744 STAUNTON ROAD", "EDWARDSVILLE", "IL", "62025")
    assert (site.names_registered, site.agent_threshold) == (3, 10)
    assert [(o.name, o.record_ids) for o in site.others] == [("ICE CREAM MAKERS INC", ["fmcsa:300"])]
    assert [m.ownership_status for m in detail.members] == ["Undisclosed Parent", "Undisclosed Parent"]


def test_a_tentative_concentration_names_the_possible_match_it_rests_on_and_the_alternatives(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    gleif(sources, "OTHER", "Brandco Foods Inc", street="1 Other Road", zip5="10001")
    sources.relationship("SUB", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])

    detail = graph.concentration(portfolio_id, only_concentration_id(graph, portfolio_id))

    holdings, brandco = detail.members
    assert (holdings.firm, holdings.match.entity_id, holdings.alternatives) == (True, "gleif:HOLD", [])
    assert (brandco.firm, brandco.match.entity_id, brandco.match.band) == (False, "gleif:SUB", "Possible")
    assert [m.entity_id for m in brandco.alternatives] == ["gleif:OTHER"]


def test_a_concentration_that_is_not_in_the_portfolio_is_not_found(sources, tmp_path):
    gleif(sources, "HOLD", "Acme Holdings Inc")
    gleif(sources, "SUB", "Brandco Foods LLC")
    sources.relationship("SUB", "HOLD", DIRECT)
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Holdings"), Member("Brandco Foods")])
    concentration_id = only_concentration_id(graph, portfolio_id)

    graph.record_verdict(portfolio_id, 2, "gleif:SUB", "rejected")

    with pytest.raises(LookupError):
        graph.concentration(portfolio_id, concentration_id)
    with pytest.raises(LookupError):
        graph.concentration("no-such-portfolio", concentration_id)


def test_a_path_through_a_cycle_stops_at_the_ultimate_parent_and_never_repeats_a_company(sources, tmp_path):
    gleif(sources, "A", "Acme Foods Inc")
    gleif(sources, "B", "Brandco Foods LLC")
    gleif(sources, "C", "Crate Foods Inc")
    for child, parent in [("A", "B"), ("B", "C"), ("C", "B")]:
        sources.relationship(child, parent, DIRECT)
    graph = opened(sources, tmp_path)
    portfolio_id = graph.create_portfolio([Member("Acme Foods"), Member("Crate Foods")])

    detail = graph.concentration(portfolio_id, only_concentration_id(graph, portfolio_id))

    assert [[s.lei for s in m.path] for m in detail.members] == [["A", "B"], ["C", "B"]]
