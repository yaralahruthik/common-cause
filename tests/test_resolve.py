from pathlib import Path

import duckdb
import pytest

from common_cause.resolve import resolve

from .raw_sources import RawSourceBuilder
from .snapshots import loaded


@pytest.fixture
def sources() -> RawSourceBuilder:
    return RawSourceBuilder()


def resolved(sources: RawSourceBuilder, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con = loaded(sources, tmp_path)
    resolve(con)
    return con


def matches(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str, str]]:
    return con.sql("select record_a, record_b, band from match order by all").fetchall()


def entities(con: duckdb.DuckDBPyConnection) -> list[list[str]]:
    """Every Entity as the sorted list of its Source Records, Entities in sorted order."""
    return [
        row[0]
        for row in con.sql(
            "select list_sort(list(record_id)) from entity_member group by entity_id order by 1"
        ).fetchall()
    ]


def gleif(sources: RawSourceBuilder, lei: str, name: str, hq_street: str, hq_zip: str, **extra: str) -> None:
    sources.lei_record(
        lei,
        name,
        **{
            "Entity.HeadquartersAddress.FirstAddressLine": hq_street,
            "Entity.HeadquartersAddress.PostalCode": hq_zip,
            "Entity.HeadquartersAddress.Region": "US-IL",
            **extra,
        },
    )


def test_registrations_with_one_name_at_one_physical_address_are_one_carrier(sources, tmp_path):
    sources.registration("100", "Acme Trucking, Inc.", phy_street="1 MAIN ST", phy_zip="60601", status_code="A")
    sources.registration("200", "ACME TRUCKING INC", phy_street="1 MAIN ST", phy_zip="60601", status_code="I")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "fmcsa:200", "Firm")]
    assert entities(con) == [["fmcsa:100", "fmcsa:200"]]


def test_two_registrations_sharing_only_a_name_are_not_matched(sources, tmp_path):
    sources.registration("100", "ACME TRUCKING INC", phy_street="1 MAIN ST", phy_zip="60601", phy_state="IL")
    sources.registration("200", "ACME TRUCKING LLC", phy_street="9 ELM ST", phy_zip="73301", phy_state="TX")

    con = resolved(sources, tmp_path)

    assert matches(con) == []
    assert entities(con) == [["fmcsa:100"], ["fmcsa:200"]]


def test_a_shared_phone_corroborates_a_name(sources, tmp_path):
    sources.registration("100", "ACME TRUCKING INC", phy_zip="60601", phone="(312) 555-0100")
    sources.registration("200", "ACME TRUCKING LLC", phy_zip="73301", phone="3125550100")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "fmcsa:200", "Firm")]


def test_a_shared_officer_corroborates_a_name(sources, tmp_path):
    sources.registration("100", "ACME TRUCKING INC", phy_zip="60601", phy_state="IL", company_officer_1="Jane Q. Roe")
    sources.registration("200", "ACME TRUCKING LLC", phy_zip="73301", phy_state="TX", company_officer_2="ROE, JANE")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "fmcsa:200", "Firm")]


def test_a_prior_revoked_number_pointer_corroborates_a_name(sources, tmp_path):
    sources.registration("100", "ACME TRUCKING INC", phy_zip="60601", status_code="I")
    sources.registration("200", "ACME TRUCKING LLC", phy_zip="73301", prior_revoke_dot_number="100")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "fmcsa:200", "Firm")]


def test_a_prior_revoked_number_pointer_under_a_new_name_is_a_possible_match(sources, tmp_path):
    sources.registration("100", "ACME TRUCKING INC", phy_zip="60601", status_code="I")
    sources.registration("200", "ZENITH HAULING LLC", phy_zip="73301", prior_revoke_dot_number="100")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "fmcsa:200", "Possible")]


def test_a_registration_naming_itself_or_zero_as_its_prior_revoked_number_is_no_pointer(sources, tmp_path):
    sources.registration("100", "ACME TRUCKING INC", phy_zip="60601", prior_revoke_dot_number="100")
    sources.registration("200", "ZENITH HAULING LLC", phy_zip="73301", prior_revoke_dot_number="0")

    con = resolved(sources, tmp_path)

    assert matches(con) == []


def test_a_similar_but_not_strong_name_with_a_corroborating_signal_is_a_possible_match(sources, tmp_path):
    sources.registration("100", "ACME FREIGHT INC", phy_street="1 MAIN ST", phy_zip="60601")
    sources.registration("200", "ACME FREIGHT SERVICES INC", phy_street="1 MAIN ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "fmcsa:200", "Possible")]


def test_unrelated_names_at_one_address_are_not_matched(sources, tmp_path):
    sources.registration("100", "ACME TRUCKING INC", phy_street="1 MAIN ST", phy_zip="60601")
    sources.registration("200", "ZENITH HAULING LLC", phy_street="1 MAIN ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert matches(con) == []


def crowd_address(sources: RawSourceBuilder, street: str, zip5: str) -> None:
    """Eleven differently named tenants at one address: more than an Agent Address allows."""
    for n in range(11):
        sources.lei_record(
            f"TENANT{n:02}",
            f"Tenant Number {n} Holdings LLC",
            **{"Entity.HeadquartersAddress.FirstAddressLine": street, "Entity.HeadquartersAddress.PostalCode": zip5},
        )


def test_an_address_shared_by_more_than_ten_names_is_an_agent_address(sources, tmp_path):
    crowd_address(sources, "251 Little Falls Drive", "19808")
    sources.registration("100", "SMALL YARD INC", phy_street="1 MAIN ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert con.sql("select street_key, zip5, names from agent_address").fetchall() == [
        ("251 LITTLE FALLS DR", "19808", 11)
    ]


def test_many_registrations_of_one_name_do_not_make_its_yard_an_agent_address(sources, tmp_path):
    for n in range(12):
        sources.registration(str(100 + n), "ACME TRUCKING INC", phy_street="1 MAIN ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert con.sql("select * from agent_address").fetchall() == []


def test_an_agent_address_does_not_corroborate_a_name(sources, tmp_path):
    crowd_address(sources, "251 Little Falls Drive", "19808")
    sources.registration("100", "ACME TRUCKING INC", phy_street="251 LITTLE FALLS DR", phy_zip="19808")
    sources.registration("200", "ACME TRUCKING LLC", phy_street="251 Little Falls Drive, Suite 100", phy_zip="19808")

    con = resolved(sources, tmp_path)

    assert matches(con) == []


def test_a_phone_shared_by_more_than_ten_names_does_not_corroborate_a_name(sources, tmp_path):
    for n in range(11):
        sources.registration(str(500 + n), f"FLEET NUMBER {n} INC", phy_zip=f"{10000 + n}", phone="8005550100")
    sources.registration("100", "ACME TRUCKING INC", phy_zip="60601", phone="8005550100")
    sources.registration("200", "ACME TRUCKING LLC", phy_zip="73301", phone="8005550100")

    con = resolved(sources, tmp_path)

    assert [m for m in matches(con) if m[0] == "fmcsa:100"] == []


def test_a_spelling_variant_in_the_same_state_is_a_possible_match(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Freight Lines, Inc.", "100 Commerce Drive", "60601")
    sources.registration("100", "ACME FREIGHT LINE INC", phy_zip="61701", phy_state="IL")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "gleif:LEI1", "Possible")]


def test_a_carrier_with_the_name_and_zip_of_a_gleif_record_is_the_same_entity(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.", "100 Commerce Drive", "60601-1234")
    sources.registration("100", "ACME FOODS INC", phy_street="4500 W 47TH ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert con.sql("select record_a, record_b, pass, band from match").fetchall() == [
        ("fmcsa:100", "gleif:LEI1", "B", "Firm")
    ]
    assert entities(con) == [["fmcsa:100", "gleif:LEI1"]]


def test_only_the_gleif_headquarters_address_is_compared(sources, tmp_path):
    gleif(
        sources,
        "LEI1",
        "Acme Foods, Inc.",
        "1 Corporate Plaza",
        "10001",
        **{"Entity.LegalAddress.FirstAddressLine": "4500 W 47TH ST", "Entity.LegalAddress.PostalCode": "60601"},
    )
    sources.registration("100", "ACME FOODS INC", phy_street="4500 W 47TH ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "gleif:LEI1", "Possible")]


def test_a_carrier_dba_name_is_matched_against_gleif(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.", "100 Commerce Drive", "60601")
    sources.registration("100", "SMITH HOLDINGS LLC", dba_name="ACME FOODS", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "gleif:LEI1", "Firm")]


def test_gleif_records_are_not_matched_to_each_other(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.", "100 Commerce Drive", "60601")
    gleif(sources, "LEI2", "Acme Foods LLC", "100 Commerce Drive", "60601")

    con = resolved(sources, tmp_path)

    assert matches(con) == []
    assert entities(con) == [["gleif:LEI1"], ["gleif:LEI2"]]


def test_entities_are_connected_through_firm_matches_but_not_possible_ones(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.", "100 Commerce Drive", "60601")
    sources.registration("100", "ACME FOODS INC", phy_street="4500 W 47TH ST", phy_zip="60601", phone="3125550100")
    sources.registration("200", "ACME FOODS LLC", phy_street="9 ELM ST", phy_zip="73301", phone="3125550100")
    sources.registration("300", "ACME FOODS CORP", phy_street="7 OAK ST", phy_zip="94105")

    con = resolved(sources, tmp_path)

    assert entities(con) == [["fmcsa:100", "fmcsa:200", "gleif:LEI1"], ["fmcsa:300"]]
    assert ("fmcsa:300", "gleif:LEI1", "Possible") in matches(con)


def test_an_entity_with_more_than_25_source_records_is_flagged(sources, tmp_path):
    for n in range(26):
        sources.registration(str(100 + n), "ACME TRUCKING INC", phy_street="1 MAIN ST", phy_zip="60601")
    sources.registration("999", "ZENITH HAULING LLC", phy_street="9 ELM ST", phy_zip="73301")

    con = resolved(sources, tmp_path)

    assert con.sql("select records, registrations, oversized from entity order by records").fetchall() == [
        (1, 1, False),
        (26, 26, True),
    ]


def test_every_match_carries_readable_evidence(sources, tmp_path):
    sources.registration(
        "100",
        "Acme Trucking, Inc.",
        phy_street="1 Main Street",
        phy_zip="60601",
        phone="3125550100",
        company_officer_1="JANE ROE",
    )
    sources.registration(
        "200", "ACME TRUCKING LLC", phy_street="1 MAIN ST", phy_zip="60601-4400", company_officer_1="Jane Roe"
    )

    con = resolved(sources, tmp_path)

    assert con.sql("select evidence from match").fetchall() == [
        (
            'names "Acme Trucking, Inc." / "ACME TRUCKING LLC" similarity 1.00; same address 1 Main Street 60601; '
            "shared officer JANE ROE",
        )
    ]


def test_a_possible_match_says_what_is_missing(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.", "100 Commerce Drive", "10001")
    sources.registration("100", "ACME FOODS INC", phy_street="4500 W 47TH ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert con.sql("select evidence from match").fetchall() == [
        ('names "ACME FOODS INC" / "Acme Foods, Inc." similarity 1.00; no corroborating signal',)
    ]


def test_names_that_share_common_words_but_differ_in_the_distinctive_one_do_not_match(sources, tmp_path):
    sources.registration("100", "PRECISE INDUSTRIAL CONSTRUCTION INC", phy_street="1 MAIN ST", phy_zip="60601")
    sources.registration("200", "STEEL INDUSTRIAL CONSTRUCTION INC", phy_street="1 MAIN ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert matches(con) == []


def test_a_one_letter_difference_in_a_short_word_is_a_different_name(sources, tmp_path):
    sources.registration("100", "ABC TRUCKING INC", phy_street="1 MAIN ST", phy_zip="60601")
    sources.registration("200", "ABD TRUCKING INC", phy_street="1 MAIN ST", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert matches(con) == []


def test_a_placeholder_dba_name_is_not_a_name(sources, tmp_path):
    sources.registration("100", "ACME TRUCKING INC", dba_name="NONE", phy_zip="60601", phy_state="IL")
    sources.registration("200", "ZENITH HAULING LLC", dba_name="N/A", phy_zip="73301", phy_state="TX")
    sources.registration("300", "APEX FREIGHT LLC", dba_name="none", phy_zip="94105", phy_state="CA")

    con = resolved(sources, tmp_path)

    assert matches(con) == []


def test_a_trade_name_shared_by_several_legal_names_is_a_brand_and_matches_nothing(sources, tmp_path):
    sources.registration("100", "LACEY ENTERPRISES LLC", dba_name="TWO MEN AND A TRUCK", phy_zip="60601")
    sources.registration("200", "KLINE LLC", dba_name="TWO MEN AND A TRUCK", phy_zip="60601")
    sources.registration("300", "WEIGT INDUSTRIES INC", dba_name="Two Men and a Truck", phy_zip="60601")

    con = resolved(sources, tmp_path)

    assert matches(con) == []


def test_a_trade_name_shared_by_two_legal_names_still_matches(sources, tmp_path):
    sources.registration("100", "SCHWARZ READY MIX OF MUSTANG INC", dba_name="SCHWARZ READY MIX", phy_zip="73099")
    sources.registration("200", "SCHWARZ READY MIX OF OKC INC", dba_name="SCHWARZ READY MIX", phy_zip="73099")

    con = resolved(sources, tmp_path)

    assert matches(con) == [("fmcsa:100", "fmcsa:200", "Firm")]


def test_a_word_that_only_shares_a_prefix_does_not_count_as_the_same_word(sources, tmp_path):
    sources.registration("100", "TRANSTAR TRANSPORTATION INC", phy_street="1 MAIN ST", phy_zip="60601")
    sources.registration(
        "200", "MERCED UNION HIGH SCHOOL DISTRICT", dba_name="TRANSPORTATION", phy_street="1 MAIN ST", phy_zip="60601"
    )

    con = resolved(sources, tmp_path)

    assert matches(con) == []


def test_a_registration_that_firmly_matches_two_gleif_records_matches_neither_firmly(sources, tmp_path):
    gleif(sources, "LEI1", "Valvoline LLC", "100 Valvoline Way", "40509")
    gleif(sources, "LEI2", "Valvoline Inc.", "100 Valvoline Way", "40509")
    sources.registration("100", "VALVOLINE LLC", phy_street="100 VALVOLINE WAY", phy_zip="40509")

    con = resolved(sources, tmp_path)

    assert con.sql("select record_a, record_b, band, evidence from match order by all").fetchall() == [
        (
            "fmcsa:100",
            "gleif:LEI1",
            "Possible",
            'names "VALVOLINE LLC" / "Valvoline LLC" similarity 1.00; same address 100 VALVOLINE WAY 40509; '
            "as strong a match for 1 other GLEIF record",
        ),
        (
            "fmcsa:100",
            "gleif:LEI2",
            "Possible",
            'names "VALVOLINE LLC" / "Valvoline Inc." similarity 1.00; same address 100 VALVOLINE WAY 40509; '
            "as strong a match for 1 other GLEIF record",
        ),
    ]
    assert entities(con) == [["fmcsa:100"], ["gleif:LEI1"], ["gleif:LEI2"]]


def test_an_entity_reaching_two_gleif_records_through_registrations_is_flagged(sources, tmp_path):
    gleif(sources, "LEI1", "Acme Foods, Inc.", "100 Commerce Drive", "60601")
    gleif(sources, "LEI2", "Acme Foods LLC", "9 Elm Street", "73301")
    sources.registration("100", "ACME FOODS INC", phy_street="4500 W 47TH ST", phy_zip="60601", phone="3125550100")
    sources.registration("200", "ACME FOODS LLC", phy_street="9 ELM ST", phy_zip="73301", phone="3125550100")

    con = resolved(sources, tmp_path)

    assert con.sql("select records, gleif_records, several_leis from entity").fetchall() == [(4, 2, True)]
