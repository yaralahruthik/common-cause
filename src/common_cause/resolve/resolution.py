"""Resolves Source Records into Entities, in SQL inside DuckDB, core functions only.

Reads the snapshot tables and writes:

- `source_record`: one row per GLEIF record and FMCSA Registration, with its comparable values.
- `agent_address`: addresses shared by so many names that they are not evidence of anything.
- `block`: every blocking key and the records that share it.
- `match`: every Firm and Possible Match, with the signals behind it and a human-readable evidence line.
- `entity_member`: every Source Record and the Entity it belongs to (connected components over Firm Matches).
- `entity`: one row per Entity, with its size and whether it is too large, or too mixed, to trust.
"""

import duckdb

from common_cause.resolve.normalise import install_macros

# An address, phone or officer shared by more than this many distinct names is a registered agent, a mail
# drop or a compliance service. It is shown, but it is never evidence for a Match.
AGENT_THRESHOLD = 10

# A trade name used by more than this many different legal names is a brand, not an identity.
BRAND_THRESHOLD = 2

# A Firm Match needs a name score at least this high and one corroborating signal.
FIRM_NAME_SCORE = 0.95
# Below FIRM_NAME_SCORE but at least this, a corroborated pair is a Possible Match. 0.8 is where a two-word
# name with one word added ("ACME FREIGHT" / "ACME FREIGHT SERVICES") lands.
POSSIBLE_NAME_SCORE = 0.8

# Characters of the sorted normalised name that form a blocking key within a state.
NAME_PREFIX_LENGTH = 8

# Blocks with more records than this are skipped: their pairs grow quadratically and a key that common
# says little. Skipped blocks are counted in the block-size report.
MAX_BLOCK_RECORDS = 1000

# Entities with more Source Records than this are flagged: a bad bridge between two real companies is
# the usual cause.
OVERSIZED_ENTITY_RECORDS = 25

SOURCE_RECORD_SQL = """
create or replace table source_record as
select
    'gleif:' || lei as record_id,
    'GLEIF' as source,
    lei as source_key,
    legal_name as name,
    normalise_name(legal_name) as name_key,
    [legal_name, other_name_1, other_name_2] as names,
    hq_address_line_1 as street,
    hq_city as city,
    regexp_replace(hq_region, '^[A-Z]{2}-', '') as state,
    hq_postal_code as postal_code,
    normalise_street(hq_address_line_1) as street_key,
    normalise_zip5(hq_postal_code) as zip5,
    null::varchar as phone_key,
    []::varchar[] as officer_keys,
    null::varchar as prior_revoke_record_id
from gleif_record
union all by name
select
    'fmcsa:' || dot_number as record_id,
    'FMCSA' as source,
    dot_number as source_key,
    legal_name as name,
    normalise_name(legal_name) as name_key,
    [legal_name, dba_name] as names,
    phy_street as street,
    phy_city as city,
    phy_state as state,
    phy_zip as postal_code,
    normalise_street(phy_street) as street_key,
    normalise_zip5(phy_zip) as zip5,
    normalise_phone(phone) as phone_key,
    list_distinct(list_filter(
        [normalise_person(company_officer_1), normalise_person(company_officer_2)], officer -> officer is not null
    )) as officer_keys,
    case
        when prior_revoke_dot_number not in ('', '0', dot_number)
        then 'fmcsa:' || prior_revoke_dot_number
    end as prior_revoke_record_id
from fmcsa_census
"""

# Every distinct normalised name a record goes by (legal name, DBA, other names), with the first published
# spelling of it for the evidence line. A trade name carried by more than a couple of different legal names is
# a brand, a franchise or a corporate family name ("TWO MEN AND A TRUCK", "COCA COLA"): it says which group a
# record belongs to, not which company it is, so it is dropped for every record that does not hold it as its
# legal name.
RECORD_NAME_SQL = """
create or replace table record_name as
with published as (
    select record_id, name_key, arg_min(published_name, position) as published_name
    from (
        select record_id, published_name, position, normalise_name(published_name) as name_key
        from (
            select record_id, unnest(names) as published_name, unnest(range(len(names))) as position
            from source_record
        )
    )
    where name_key <> ''
    group by all
),
trade_name as (
    select published.record_id, published.name_key, source_record.name_key as legal_name_key
    from published
    join source_record using (record_id)
    where published.name_key <> source_record.name_key
),
brand as (
    select name_key from trade_name group by all having count(distinct legal_name_key) > $brand
)
select * from published
anti join (select record_id, name_key from trade_name semi join brand using (name_key)) using (record_id, name_key)
"""

# An address only counts once street and ZIP are both known. Distinct names stand in for distinct Entities,
# which do not exist yet: several Registrations of one carrier at its yard must not make the yard an agent.
AGENT_ADDRESS_SQL = """
create or replace table agent_address as
select street_key, zip5, count(distinct name_key) as names, count(*) as records
from source_record
where street_key is not null and zip5 is not null and name_key <> ''
group by all
having count(distinct name_key) > $threshold
"""

# Records whose own physical or headquarters address is not an Agent Address: the only addresses that are evidence.
EVIDENTIAL_ADDRESS_SQL = """
create or replace temp view evidential_address as
select record_id, street_key, zip5
from source_record
anti join agent_address using (street_key, zip5)
where zip5 is not null
"""

CROWDED_PHONE_SQL = """
create or replace temp table crowded_phone as
select phone_key from source_record where phone_key is not null and name_key <> ''
group by all having count(distinct name_key) > $threshold
"""

CROWDED_OFFICER_SQL = """
create or replace temp table crowded_officer as
select officer_key from (select unnest(officer_keys) as officer_key, name_key from source_record where name_key <> '')
group by all having count(distinct name_key) > $threshold
"""

TOKEN_FREQUENCY_SQL = """
create or replace temp table token_frequency as
select token, count(distinct record_id) as records
from (select record_id, unnest(string_split(name_key, ' ')) as token from record_name)
group by all
"""

# Blocking keys. A candidate pair is any two records sharing a key. Within a state, the rarest token of a
# name catches added or dropped words, and the start of the sorted name catches a misspelt last word.
BLOCK_SQL = """
create or replace table block as
select distinct record_id, block_key from (
    select record_id, 'name:' || name_key as block_key from record_name
    union all
    select rarest.record_id, 'token:' || rarest.token || ':' || source_record.state
    from (
        select record_id, name_key, arg_min(token, (records, token)) as token
        from (select record_id, name_key, unnest(string_split(name_key, ' ')) as token from record_name)
        join token_frequency using (token)
        group by all
    ) as rarest
    join source_record using (record_id)
    where source_record.state <> ''
    union all
    select record_id, 'prefix:' || left(record_name.name_key, $prefix) || ':' || state
    from record_name
    join source_record using (record_id)
    where state <> ''
    union all
    select record_id, 'address:' || street_key || '|' || zip5 from evidential_address where street_key is not null
    union all
    select record_id, 'phone:' || phone_key from source_record anti join crowded_phone using (phone_key)
    where phone_key is not null
    union all
    select record_id, 'officer:' || officer_key || ':' || state
    from (select record_id, state, unnest(officer_keys) as officer_key from source_record)
    anti join crowded_officer using (officer_key)
)
"""

BLOCK_SIZE_SQL = """
create or replace table block_size as
select block_key, count(*) as records from block group by all
"""

# Pairs are ordered so the FMCSA record comes first in Pass B ('fmcsa:' sorts before 'gleif:').
# GLEIF-to-GLEIF pairs are not compared: an LEI already identifies one legal entity.
CANDIDATE_SQL = """
create or replace temp table candidate as
select distinct record_a, record_b from (
    select a.record_id as record_a, b.record_id as record_b
    from block as a
    join block as b on a.block_key = b.block_key and a.record_id < b.record_id and a.record_id like 'fmcsa:%'
    where a.block_key in (select block_key from block_size where records <= $max_block)
    union all
    select least(record_id, prior_revoke_record_id), greatest(record_id, prior_revoke_record_id)
    from source_record
    where prior_revoke_record_id in (select record_id from source_record)
)
where record_a like 'fmcsa:%'
"""

SIGNAL_SQL = """
create or replace temp table pair_signal as
with name_score as (
    select
        record_a,
        record_b,
        max(name_similarity(name_a.name_key, name_b.name_key)) as name_score,
        arg_max([name_a.published_name, name_b.published_name], name_similarity(name_a.name_key, name_b.name_key))
            as best_names
    from candidate
    join record_name as name_a on name_a.record_id = candidate.record_a
    join record_name as name_b on name_b.record_id = candidate.record_b
    group by all
),
shared_officer as (
    select record_a, record_b, list(officer_key order by officer_key) as shared_officers
    from (
        select record_a, record_b, unnest(list_intersect(a.officer_keys, b.officer_keys)) as officer_key
        from candidate
        join source_record as a on a.record_id = candidate.record_a
        join source_record as b on b.record_id = candidate.record_b
    )
    anti join crowded_officer using (officer_key)
    group by all
)
select
    candidate.record_a,
    candidate.record_b,
    case when b.source = 'FMCSA' then 'A' else 'B' end as pass,
    coalesce(name_score.name_score, 0) as name_score,
    name_score.best_names,
    coalesce(address_a.street_key = address_b.street_key and address_a.zip5 = address_b.zip5, false) as same_address,
    coalesce(address_a.zip5 = address_b.zip5, false) as same_zip,
    coalesce(a.phone_key = b.phone_key and a.phone_key not in (select phone_key from crowded_phone), false)
        as same_phone,
    coalesce(shared_officer.shared_officers, []) as shared_officers,
    coalesce(a.prior_revoke_record_id = b.record_id or b.prior_revoke_record_id = a.record_id, false) as prior_revoke,
    a.street as street_a,
    a.postal_code as postal_code_a,
    b.street as street_b,
    b.postal_code as postal_code_b,
    a.phone_key as phone
from candidate
join source_record as a on a.record_id = candidate.record_a
join source_record as b on b.record_id = candidate.record_b
left join name_score using (record_a, record_b)
left join shared_officer using (record_a, record_b)
left join evidential_address as address_a on address_a.record_id = candidate.record_a
left join evidential_address as address_b on address_b.record_id = candidate.record_b
"""

MATCH_SQL = """
create or replace table match as
with scored as (
    select
        *,
        (same_zip::int + same_phone::int + (len(shared_officers) > 0)::int + prior_revoke::int) as corroborators
    from pair_signal
),
banded as (
    select
        *,
        case
            when name_score >= $firm and corroborators > 0 then 'Firm'
            -- Within FMCSA, a shared name with nothing else shared is a different carrier far more often than
            -- not (0 of 15 hand-labelled pairs were the same). Against GLEIF it is worth showing: a fleet is often
            -- registered at a plant while the company files from its headquarters.
            when name_score >= $firm and pass = 'B' then 'Possible'
            when name_score >= $possible and corroborators > 0 then 'Possible'
            when prior_revoke then 'Possible'
        end as rule_band
    from scored
),
-- An LEI is one legal entity, so a Registration can be firmly one of them at most. When it is as strongly
-- matched to several (a parent and a subsidiary with one name at one address), none of them is asserted.
disambiguated as (
    select
        *,
        count(*) filter (where pass = 'B' and rule_band = 'Firm') over (partition by record_a) - 1 as rival_leis
    from banded
    where rule_band is not null
)
select
    record_a,
    record_b,
    pass,
    case when pass = 'B' and rule_band = 'Firm' and rival_leis > 0 then 'Possible' else rule_band end as band,
    round(name_score, 3) as name_score,
    same_address,
    same_zip,
    same_phone,
    shared_officers,
    prior_revoke,
    concat_ws('; ',
        format('names "{}" / "{}" similarity {:.2f}', best_names[1], best_names[2], name_score),
        case
            when same_address then format('same address {} {}', street_a, postal_code_a)
            when same_zip then format('same ZIP {} ({} / {})', left(postal_code_a, 5), street_a, street_b)
        end,
        case when same_phone then format('same phone {}', phone) end,
        case when len(shared_officers) > 0 then 'shared officer ' || array_to_string(shared_officers, ', ') end,
        case when prior_revoke then 'registry names one as the prior revoked number of the other' end,
        case when corroborators = 0 then 'no corroborating signal' end,
        case
            when pass = 'B' and rule_band = 'Firm' and rival_leis > 0
            then format('as strong a match for {} other GLEIF record{}', rival_leis, if(rival_leis > 1, 's', ''))
        end
    ) as evidence
from disambiguated
"""

# Connected components over Firm Matches by label propagation: every record starts as its own Entity and
# repeatedly takes the smallest Entity id among its Firm-matched neighbours until nothing changes.
FIRM_EDGE_SQL = """
create or replace temp table firm_edge as
select record_a as record_id, record_b as neighbour from match where band = 'Firm'
union all
select record_b, record_a from match where band = 'Firm'
"""

PROPAGATE_SQL = """
create or replace temp table next_member as
select member.record_id, least(member.entity_id, min(neighbour_member.entity_id)) as entity_id
from entity_member as member
left join firm_edge using (record_id)
left join entity_member as neighbour_member on neighbour_member.record_id = firm_edge.neighbour
group by member.record_id, member.entity_id
"""

ENTITY_SQL = """
create or replace table entity as
select
    entity_id,
    count(*) as records,
    count(*) filter (where source = 'GLEIF') as gleif_records,
    count(*) filter (where source = 'FMCSA') as registrations,
    count(*) > $oversized as oversized,
    -- Two LEIs are two legal entities, so an Entity holding both was bridged by a wrong Firm Match somewhere.
    count(*) filter (where source = 'GLEIF') > 1 as several_leis
from entity_member
join source_record using (record_id)
group by entity_id
"""


def resolve(con: duckdb.DuckDBPyConnection) -> None:
    """Builds the resolution tables from the snapshot tables already loaded into `con`."""
    install_macros(con)
    con.execute(SOURCE_RECORD_SQL)
    con.execute(RECORD_NAME_SQL, {"brand": BRAND_THRESHOLD})
    con.execute(AGENT_ADDRESS_SQL, {"threshold": AGENT_THRESHOLD})
    con.execute(EVIDENTIAL_ADDRESS_SQL)
    con.execute(CROWDED_PHONE_SQL, {"threshold": AGENT_THRESHOLD})
    con.execute(CROWDED_OFFICER_SQL, {"threshold": AGENT_THRESHOLD})
    con.execute(TOKEN_FREQUENCY_SQL)
    con.execute(BLOCK_SQL, {"prefix": NAME_PREFIX_LENGTH})
    con.execute(BLOCK_SIZE_SQL)
    con.execute(CANDIDATE_SQL, {"max_block": MAX_BLOCK_RECORDS})
    con.execute(SIGNAL_SQL)
    con.execute(MATCH_SQL, {"firm": FIRM_NAME_SCORE, "possible": POSSIBLE_NAME_SCORE})
    _connected_components(con)
    con.execute(ENTITY_SQL, {"oversized": OVERSIZED_ENTITY_RECORDS})


def _connected_components(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(FIRM_EDGE_SQL)
    con.execute("create or replace table entity_member as select record_id, record_id as entity_id from source_record")
    while True:
        con.execute(PROPAGATE_SQL)
        changed = con.execute(
            "select count(*) from next_member join entity_member using (record_id) "
            "where next_member.entity_id <> entity_member.entity_id"
        ).fetchall()[0][0]
        con.execute("create or replace table entity_member as select * from next_member")
        if changed == 0:
            return
