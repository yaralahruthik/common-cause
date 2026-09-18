import duckdb
import pytest

from common_cause.resolve.normalise import install_macros


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    install_macros(con)
    return con


@pytest.mark.parametrize(
    ("published", "normalised"),
    [
        ("Acme Trucking, Inc.", "ACME TRUCKING"),
        ("ACME TRUCKING INC", "ACME TRUCKING"),
        ("Société Générale", "GENERALE SOCIETE"),
        ("Trucking Acme LLC", "ACME TRUCKING"),
        ("ACME TRUCKING L.L.C.", "ACME TRUCKING"),
        ("ACME TRUCKING L L C", "ACME TRUCKING"),
        ("The Acme Trucking Company", "ACME TRUCKING"),
        ("ACME TRUCKING CORP", "ACME TRUCKING"),
        ("Acme Trucking Corporation", "ACME TRUCKING"),
        ("ACME TRUCKING INCORPORATED", "ACME TRUCKING"),
        ("Acme Trucking Limited", "ACME TRUCKING"),
        ("ACME TRUCKING LTD", "ACME TRUCKING"),
        ("Acme Holdings, L.P.", "ACME HOLDINGS"),
        ("Acme Partners LLP", "ACME PARTNERS"),
        ("Acme Dental, P.C.", "ACME DENTAL"),
        ("Acme Law PLLC", "ACME LAW"),
        ("Smith & Sons Hauling", "HAULING SMITH SONS"),
        ("Smith and Sons Hauling", "HAULING SMITH SONS"),
        ("O'Brien Brothers", "BROTHERS OBRIEN"),
        ("U.S. Freight", "FREIGHT S U"),
        ("U S FREIGHT", "FREIGHT S U"),
        ("Smith-Jones Freight", "FREIGHT JONES SMITH"),
        ("City of Palmdale", "CITY PALMDALE"),
        ("  Acme   Trucking  ", "ACME TRUCKING"),
        ("", ""),
        ("N/A", ""),
        ("none", ""),
        ("Not Applicable", ""),
        ("ΡΕΝΤΕΝ ΕΡΜΕΣ 2 ΜΟΝΟΠΡΟΣΩΠΗ", ""),
        ("L.E.S. Corp", ""),
        ("D J Trucking", "D J TRUCKING"),
    ],
)
def test_normalise_name(con, published, normalised):
    assert con.execute("select normalise_name(?)", [published]).fetchone() == (normalised,)


def test_a_name_made_only_of_legal_forms_normalises_to_nothing(con):
    assert con.execute("select normalise_name('Inc.')").fetchone() == ("",)


def test_a_missing_name_stays_missing(con):
    assert con.execute("select normalise_name(null)").fetchone() == (None,)


@pytest.mark.parametrize(
    ("published", "normalised"),
    [
        ("1 Main Street", "1 MAIN ST"),
        ("1 MAIN ST.", "1 MAIN ST"),
        ("9160 Bursa Road, Suite A", "9160 BURSA RD"),
        ("9160 BURSA RD STE 200", "9160 BURSA RD"),
        ("214 W 39TH ST RM 902", "214 W 39TH ST"),
        ("1 Main St #4", "1 MAIN ST"),
        ("100 North Commerce Drive, Floor 3", "100 N COMMERCE DR"),
        ("", None),
    ],
)
def test_normalise_street(con, published, normalised):
    assert con.execute("select normalise_street(?)", [published]).fetchone() == (normalised,)


@pytest.mark.parametrize(
    ("published", "normalised"),
    [("60601", "60601"), ("53562-4244", "53562"), ("536", None), ("M5V 2T6", None), ("", None)],
)
def test_normalise_zip5(con, published, normalised):
    assert con.execute("select normalise_zip5(?)", [published]).fetchone() == (normalised,)


@pytest.mark.parametrize(
    ("published", "normalised"),
    [("(312) 555-0100", "3125550100"), ("1-312-555-0100", "3125550100"), ("5550100", None), ("", None)],
)
def test_normalise_phone(con, published, normalised):
    assert con.execute("select normalise_phone(?)", [published]).fetchone() == (normalised,)


@pytest.mark.parametrize(
    ("published", "normalised"),
    [("Jane Q. Roe", "JANE ROE"), ("ROE, JANE", "JANE ROE"), ("José  Núñez", "JOSE NUNEZ"), ("", None)],
)
def test_normalise_person(con, published, normalised):
    assert con.execute("select normalise_person(?)", [published]).fetchone() == (normalised,)
