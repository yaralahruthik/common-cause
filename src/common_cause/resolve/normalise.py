"""SQL macros that put registry values into a comparable form. DuckDB core functions only."""

import duckdb

# Legal forms and filler words dropped from names. Spelled-out multi-letter forms ("L L C") are handled
# separately because they only exist as a run of single-letter tokens.
NAME_STOPWORDS = (
    "INC",
    "INCORPORATED",
    "LLC",
    "LLP",
    "LP",
    "PLLC",
    "PC",
    "LTD",
    "LIMITED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "THE",
    "AND",
    "OF",
)
SPELLED_LEGAL_FORMS = r"\b(P L L C|L L C|L L P|L P|P C)\b"

# What registrants type into an optional name field when they have nothing to put there, once normalised.
PLACEHOLDER_NAMES = ("NONE", "A N", "NA", "SAME", "UNKNOWN", "APPLICABLE NOT")

# Uppercase and strip accents; drop apostrophes so "O'BRIEN" stays one word; every other run of punctuation
# becomes a space, so "U.S." and "U S" agree; drop legal forms; sort the tokens so word order stops mattering.
# A placeholder such as "N/A", and a name with no word of two or more Latin letters (initials only, or a name in
# another script), normalise to nothing: there is nothing distinctive left to compare.
NORMALISE_NAME = f"""
create or replace macro normalise_name_tokens(name) as array_to_string(
    list_sort(list_filter(
        string_split(
            regexp_replace(
                regexp_replace(
                    regexp_replace(upper(strip_accents(name)), '''', '', 'g'),
                    '[^A-Z0-9]+', ' ', 'g'
                ),
                '{SPELLED_LEGAL_FORMS}', ' ', 'g'
            ),
            ' '
        ),
        token -> token <> '' and token not in {NAME_STOPWORDS!r}
    )),
    ' '
);

create or replace macro normalise_name(name) as
    case
        when normalise_name_tokens(name) in {PLACEHOLDER_NAMES!r} then ''
        when not regexp_matches(normalise_name_tokens(name), '[A-Z]{{2}}') then ''
        else normalise_name_tokens(name)
    end
"""

# Similarity of two normalised names, 0 to 1: every token of each name is paired with its closest token in the
# other by Jaro-Winkler, and the scores are averaged over all tokens. A closest token scoring under
# SAME_WORD_SCORE is a different word and scores 0, so "TRANSTAR" is not half of "TRANSPORTATION", while a
# misspelling ("FRIEGHT") still counts. Scoring the sorted strings directly would let shared leading words
# carry a pair ("CONSTRUCTION INDUSTRIAL PRECISE" / "... STEEL" scores 0.95). A name that is a subset of
# another scores below 1, however exact the shared words.
SAME_WORD_SCORE = 0.9
NAME_SIMILARITY = f"""
create or replace macro best_token_scores(a, b) as list_transform(
    string_split(a, ' '),
    t -> list_max(list_transform(
        string_split(b, ' '),
        u -> case when jaro_winkler_similarity(t, u) >= {SAME_WORD_SCORE} then jaro_winkler_similarity(t, u) else 0 end
    ))
);

create or replace macro name_similarity(a, b) as
    (list_sum(best_token_scores(a, b)) + list_sum(best_token_scores(b, a)))
    / (len(string_split(a, ' ')) + len(string_split(b, ' ')))
"""


# Street words as the USPS abbreviates them, so "1 Main Street" and "1 MAIN ST" agree.
STREET_ABBREVIATIONS = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "AV": "AVE",
    "ROAD": "RD",
    "DRIVE": "DR",
    "BOULEVARD": "BLVD",
    "LANE": "LN",
    "COURT": "CT",
    "PLACE": "PL",
    "PARKWAY": "PKWY",
    "HIGHWAY": "HWY",
    "CIRCLE": "CIR",
    "TERRACE": "TER",
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
}

# The street line without its suite, unit or floor: a mail drop and its tenants differ only there.
SUITE_AND_AFTER = r"(\b(SUITE|STE|UNIT|FLOOR|FL|RM|ROOM)\b|#).*$"
NORMALISE_STREET = f"""
create or replace macro normalise_street(street) as nullif(array_to_string(
    list_transform(
        list_filter(
            string_split(
                regexp_replace(
                    regexp_replace(upper(strip_accents(street)), '{SUITE_AND_AFTER}', ''),
                    '[^A-Z0-9]+', ' ', 'g'
                ),
                ' '
            ),
            token -> token <> ''
        ),
        token -> coalesce(map {STREET_ABBREVIATIONS!r}[token], token)
    ),
    ' '
), '')
"""

# First five digits of a US ZIP code; anything shorter is not a ZIP.
NORMALISE_ZIP5 = """
create or replace macro normalise_zip5(postal_code) as
    case when regexp_matches(postal_code, '^\\s*[0-9]{5}') then left(trim(postal_code), 5) end
"""

# Ten-digit North American number, or nothing.
NORMALISE_PHONE = """
create or replace macro normalise_phone(phone) as (
    with digits as (select regexp_replace(phone, '[^0-9]', '', 'g') as d)
    select case
        when length(d) = 11 and d[1] = '1' then d[2:]
        when length(d) = 10 then d
    end
    from digits
)
"""

# A person's name with punctuation and initials dropped and tokens sorted, so "SMITH, JOHN A." = "JOHN SMITH".
NORMALISE_PERSON = """
create or replace macro normalise_person(person) as nullif(array_to_string(
    list_sort(list_filter(
        string_split(regexp_replace(upper(strip_accents(person)), '[^A-Z]+', ' ', 'g'), ' '),
        token -> length(token) > 1
    )),
    ' '
), '')
"""


def install_macros(con: duckdb.DuckDBPyConnection) -> None:
    for macro in (NORMALISE_NAME, NAME_SIMILARITY, NORMALISE_STREET, NORMALISE_ZIP5, NORMALISE_PHONE, NORMALISE_PERSON):
        con.execute(macro)
