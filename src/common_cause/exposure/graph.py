"""The graph the API serves: a resolved snapshot, Portfolios matched into it, and their Hidden Concentrations.

Everything is read from one in-memory DuckDB connection built at start-up (snapshot, resolution, Ultimate
Parents). Portfolios and Verdicts are the only writes; they live in a separate DuckDB file attached to the same
connection, and a lock makes that connection the single writer (docs/adr/0001-duckdb-as-the-graph-store.md).
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from common_cause.exposure.ownership import build_ownership
from common_cause.ingest.snapshot import load_snapshot
from common_cause.resolve import resolve
from common_cause.resolve.resolution import POSSIBLE_NAME_SCORE

# A Portfolio name without a unique exact hit is offered at most this many Possible Matches.
MAX_POSSIBLE_MATCHES = 3

VERDICTS = ("confirmed", "rejected")

# Common Causes in the order they are listed when their share of the Portfolio ties.
CAUSE_KINDS = ["Ultimate Parent", "Address", "Jurisdiction"]

# Listed after every other Common Cause, however large its share: most US companies are incorporated in a handful of
# states, so a shared jurisdiction is nearly always the largest concentration and the least telling one.
LAST_CAUSE_KIND = "Jurisdiction"

# Portfolios and Verdicts. Members are numbered from 1 in the order they were given. A Verdict is stored against the
# Source Record the Match was made through, not the Entity: Entity ids are recomputed whenever the snapshot is
# resolved, while a record id (an LEI or a USDOT number) is not.
WORKSPACE_SQL = """
create table if not exists workspace.portfolio (portfolio_id varchar primary key, created_at timestamp);
create table if not exists workspace.portfolio_member (
    portfolio_id varchar, member_id integer, name varchar, state varchar, city varchar,
    primary key (portfolio_id, member_id)
);
create table if not exists workspace.verdict (
    portfolio_id varchar, member_id integer, record_id varchar, verdict varchar, decided_at timestamp,
    primary key (portfolio_id, member_id, record_id)
);
"""

# Every word of every name a record goes by: a Portfolio name is only scored against records sharing a word with it.
NAME_TOKEN_SQL = """
create or replace table name_token as
select record_id, name_key, published_name, unnest(string_split(name_key, ' ')) as token
from record_name
"""

# What each Entity could share with another: the Ultimate Parent of each of its LEIs, each of its physical or
# headquarters addresses that is not an Agent Address, and each GLEIF legal jurisdiction. FMCSA publishes no
# ownership and no jurisdiction, so a Carrier with no GLEIF record can only share an address.
ENTITY_CAUSE_SQL = """
create or replace table entity_cause as
with entity_lei as (
    select entity_id, source_key as lei
    from entity_member join source_record using (record_id)
    where source = 'GLEIF'
)
select distinct entity_id, 'Ultimate Parent' as kind, ultimate_parent_lei as key,
    coalesce(parent.legal_name, 'LEI ' || ultimate_parent_lei) as label
from entity_lei
join ultimate_parent using (lei)
left join gleif_record as parent on parent.lei = ultimate_parent.ultimate_parent_lei
union all
select distinct entity_id, 'Address', street_key || ', ' || zip5, street_key || ', ' || zip5
from entity_member
join source_record using (record_id)
anti join agent_address using (street_key, zip5)
where street_key is not null and zip5 is not null
union all
select distinct entity_id, 'Jurisdiction', legal_jurisdiction, legal_jurisdiction
from entity_lei join gleif_record using (lei)
where legal_jurisdiction <> ''
"""

# A Portfolio name is matched to Entities by the names their records go by. One Entity with the exact normalised
# name (within the state and city, when given) is a Firm Match. The closest other Entities scoring at least
# POSSIBLE_NAME_SCORE are Possible Matches, exact hits shared by several Entities included. They are kept beside a
# Firm Match so that an analyst who rejects it still has the near names to confirm.
PORTFOLIO_MATCH_SQL = """
create or replace temp table portfolio_match as
with query as (
    select
        member_id,
        normalise_name(name) as name_key,
        nullif(upper(trim(state)), '') as state,
        nullif(upper(trim(city)), '') as city
    from workspace.portfolio_member
    where portfolio_id = $portfolio
),
query_token as (
    select distinct member_id, unnest(string_split(name_key, ' ')) as token from query where name_key <> ''
),
candidate as (
    select distinct member_id, record_id, name_token.name_key, published_name
    from query_token join name_token using (token)
),
scored as (
    select
        candidate.member_id,
        entity_member.entity_id,
        candidate.record_id,
        candidate.published_name,
        source_record.city,
        source_record.state,
        name_similarity(query.name_key, candidate.name_key) as score,
        query.name_key = candidate.name_key as exact,
        concat_ws(', ', query.city, query.state) as searched_in
    from candidate
    join query using (member_id)
    join source_record using (record_id)
    join entity_member using (record_id)
    where (query.state is null or upper(source_record.state) = query.state)
        and (query.city is null or upper(trim(source_record.city)) = query.city)
),
best as (
    select * from scored
    where score >= $possible
    qualify row_number() over (partition by member_id, entity_id order by score desc, record_id) = 1
),
counted as (
    select *, count(*) filter (where exact) over (partition by member_id) as exact_entities from best
),
-- The latest Verdict on any record of the Entity as it is resolved now.
entity_verdict as (
    select verdict.member_id, entity_member.entity_id, arg_max(verdict.verdict, verdict.decided_at) as verdict
    from workspace.verdict as verdict
    join entity_member using (record_id)
    where verdict.portfolio_id = $portfolio
    group by all
)
select
    counted.member_id,
    counted.entity_id,
    case when exact_entities = 1 and exact then 'Firm' else 'Possible' end as band,
    round(score, 3) as score,
    record_id,
    published_name as name,
    city,
    state,
    concat_ws('; ',
        case
            when exact_entities = 1 and exact then format('only Entity with the name "{}"', published_name)
            when exact then format('name "{}" matches exactly, as do {} other Entities', published_name,
                exact_entities - 1)
            else format('name "{}" similarity {:.2f}', published_name, score)
        end,
        case when searched_in <> '' then 'searched within ' || searched_in end
    ) as evidence,
    entity_verdict.verdict
from counted
left join entity_verdict
    on entity_verdict.member_id = counted.member_id and entity_verdict.entity_id = counted.entity_id
qualify row_number() over (partition by counted.member_id, band order by score desc, counted.entity_id)
    <= $max_possible
"""

# A new Verdict on an Entity replaces every earlier one the member was given on any of its records.
REPLACED_VERDICT_SQL = """
delete from workspace.verdict
where portfolio_id = $portfolio and member_id = $member
    and record_id in (select record_id from entity_member where entity_id = $entity)
"""

# What the analyst's Verdicts leave standing: a Firm or confirmed Match holds and hides the member's other
# Matches; unjudged Possible Matches are carried as not firm; a rejected Match is gone.
MEMBER_ENTITY_SQL = """
create or replace temp table member_entity as
select member_id, entity_id, band = 'Firm' or verdict is not distinct from 'confirmed' as firm
from portfolio_match
where verdict is distinct from 'rejected'
qualify firm or not bool_or(firm) over (partition by member_id)
"""

# A Hidden Concentration is a Common Cause shared by two or more members that are different Entities: two names for
# one company are not independent to begin with. It is tentative unless two different Entities reach it through Firm
# or confirmed Matches. Its share counts only firmly matched members; the share it would have if every Possible
# Match held is given beside it, and breaks ties.
CONCENTRATION_SQL = """
select
    kind,
    key,
    any_value(label) as label,
    count(distinct member_id) filter (where firm) / $total as share,
    count(distinct member_id) / $total as share_if_possible_matches_hold,
    count(distinct member_id) filter (where firm) < 2 or count(distinct entity_id) filter (where firm) < 2
        as tentative
from member_entity
join entity_cause using (entity_id)
group by kind, key
having count(distinct member_id) >= 2 and count(distinct entity_id) >= 2
order by kind = $last_kind, share desc, share_if_possible_matches_hold desc, tentative, list_position($kinds, kind),
    label
"""

# Each member of each concentration, firmest Entity first, with the ownership path from the member to the
# Ultimate Parent when that is the cause.
CONCENTRATION_MEMBER_SQL = """
with member_cause as (
    select kind, key, member_id, member.name, entity_id, firm
    from member_entity
    join entity_cause using (entity_id)
    join workspace.portfolio_member as member using (member_id)
    where member.portfolio_id = $portfolio
    qualify row_number() over (partition by kind, key, member_id order by firm desc, entity_id) = 1
),
walked as (
    select entity_id, ultimate_parent_lei as key, arg_min(path, len(path)) as path
    from member_entity
    join entity_member using (entity_id)
    join source_record using (record_id)
    join ultimate_parent on ultimate_parent.lei = source_record.source_key
    where source_record.source = 'GLEIF'
    group by all
),
step as (
    select entity_id, key, n, lei, legal_name
    from (select entity_id, key, unnest(path) as lei, unnest(range(len(path))) as n from walked)
    left join gleif_record using (lei)
),
named_path as (
    select entity_id, key, list({'lei': lei, 'name': legal_name} order by n) as path from step group by all
)
select
    member_cause.kind,
    member_cause.key,
    member_cause.member_id,
    member_cause.name,
    member_cause.entity_id,
    member_cause.firm,
    coalesce(named_path.path, []) as path
from member_cause
left join named_path on member_cause.kind = 'Ultimate Parent' and named_path.entity_id = member_cause.entity_id
    and named_path.key = member_cause.key
order by member_cause.member_id
"""

# Ownership Status per member, from the LEIs of its Firm or confirmed Entity. An Entity holding several LEIs is
# given the least verifiable of their statuses, and one with no GLEIF record has an Undisclosed Parent: nothing
# about its ownership is known. A member with no firm Entity has no Ownership Status yet, because it is not yet
# known which company it is.
MEMBER_OWNERSHIP_SQL = """
with firm_status as (
    select
        member_id,
        arg_min(
            {'status': ownership_status, 'basis': ownership_basis},
            list_position(['Undisclosed Parent', 'Declared Independent', 'Declared Parent'], ownership_status)
        ) as known,
        true as matched
    from member_entity
    left join entity_member using (entity_id)
    left join source_record on source_record.record_id = entity_member.record_id and source = 'GLEIF'
    left join gleif_ownership_status on gleif_ownership_status.lei = source_record.source_key
    where firm
    group by member_id
)
select
    member_id,
    member.name,
    case when matched then coalesce(known.status, 'Undisclosed Parent') end as status,
    case when matched is null then 'no Firm Match' else coalesce(known.basis, 'no GLEIF record') end as basis
from workspace.portfolio_member as member
left join firm_status using (member_id)
where member.portfolio_id = $portfolio
order by member_id
"""

# Members whose walked Ultimate Parent is not the one their registry entry declares.
DISAGREEMENT_SQL = """
select distinct member_id, member.name, lei, path[-1] as walked_lei, declared_ultimate_parent_lei
from member_entity
join entity_member using (entity_id)
join source_record using (record_id)
join ultimate_parent on ultimate_parent.lei = source_record.source_key
join workspace.portfolio_member as member using (member_id)
where firm and source = 'GLEIF' and disagrees and member.portfolio_id = $portfolio
order by member_id, lei
"""

AS_OF_SQL = """
select 'GLEIF', max(as_of_date) from gleif_record
union all select 'FMCSA census', max(as_of_date) from fmcsa_census
union all select 'FMCSA out-of-service orders', max(as_of_date) from fmcsa_oos_order
"""


@dataclass(frozen=True)
class Member:
    """One line of a Portfolio as the analyst gave it."""

    name: str
    state: str | None = None
    city: str | None = None


@dataclass(frozen=True)
class Match:
    """A proposed pairing of a Portfolio member to one Entity, and the analyst's Verdict on it if any."""

    entity_id: str
    band: str
    score: float
    record_id: str
    name: str
    city: str
    state: str
    evidence: str
    verdict: str | None


@dataclass(frozen=True)
class PortfolioMember:
    member_id: int
    name: str
    state: str | None
    city: str | None
    matches: list[Match]


@dataclass(frozen=True)
class PathStep:
    lei: str
    name: str | None


@dataclass(frozen=True)
class ConcentrationMember:
    member_id: int
    name: str
    entity_id: str
    firm: bool
    # From the member's LEI up to the Ultimate Parent; empty for other Common Causes.
    path: list[PathStep]


@dataclass(frozen=True)
class Concentration:
    kind: str
    key: str
    label: str
    # Members matched firmly, as a share of the Portfolio; and the share if every Possible Match held.
    share: float
    share_if_possible_matches_hold: float
    tentative: bool
    members: list[ConcentrationMember]


@dataclass(frozen=True)
class MemberOwnership:
    member_id: int
    name: str
    # None until the member has a Firm or confirmed Match.
    status: str | None
    basis: str


@dataclass(frozen=True)
class Disagreement:
    member_id: int
    name: str
    lei: str
    walked_lei: str
    declared_lei: str


@dataclass(frozen=True)
class Ownership:
    total: int
    # Members with a Firm or confirmed Match, and those without one.
    matched: int
    unmatched: int
    # Matched members whose ownership cannot be verified: an Undisclosed Parent.
    unverifiable: int
    members: list[MemberOwnership]
    disagreements: list[Disagreement]


@dataclass(frozen=True)
class Exposure:
    portfolio_id: str
    members: int
    concentrations: list[Concentration]
    ownership: Ownership
    as_of: dict[str, date]


class Graph:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con
        self._lock = threading.Lock()

    @classmethod
    def open(cls, snapshot_dir: Path, workspace_path: Path) -> "Graph":
        """Loads and resolves the snapshot, and attaches the file holding Portfolios and Verdicts."""
        con = duckdb.connect()
        con.execute("set enable_progress_bar = false")
        load_snapshot(con, snapshot_dir)
        resolve(con)
        build_ownership(con)
        con.execute(NAME_TOKEN_SQL)
        con.execute(ENTITY_CAUSE_SQL)
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"attach '{_sql_string(workspace_path)}' as workspace")
        con.execute(WORKSPACE_SQL)
        return cls(con)

    def close(self) -> None:
        with self._lock:
            self._con.close()

    def create_portfolio(self, members: list[Member]) -> str:
        if not members:
            raise ValueError("a Portfolio needs at least one member")
        portfolio_id = uuid.uuid4().hex
        with self._lock:
            self._con.begin()
            self._con.execute("insert into workspace.portfolio values (?, now())", [portfolio_id])
            self._con.executemany(
                "insert into workspace.portfolio_member values (?, ?, ?, ?, ?)",
                [[portfolio_id, n, m.name, m.state, m.city] for n, m in enumerate(members, start=1)],
            )
            self._con.commit()
        return portfolio_id

    def portfolio(self, portfolio_id: str) -> list[PortfolioMember]:
        """Every member with its Matches, best first."""
        with self._lock:
            self._match(portfolio_id)
            members = self._rows(
                "select member_id, name, state, city from workspace.portfolio_member where portfolio_id = ? "
                "order by member_id",
                [portfolio_id],
            )
            matches = self._rows(
                "select * exclude (member_id), member_id from portfolio_match order by member_id, score desc, entity_id"
            )
        by_member: dict[int, list[Match]] = {m["member_id"]: [] for m in members}
        for row in matches:
            by_member[row.pop("member_id")].append(Match(**row))
        return [PortfolioMember(**m, matches=by_member[m["member_id"]]) for m in members]

    def record_verdict(self, portfolio_id: str, member_id: int, entity_id: str, verdict: str) -> None:
        """Confirms or rejects one of a member's Matches, for this Portfolio only. A new Verdict replaces the old."""
        if verdict not in VERDICTS:
            raise ValueError(f"a Verdict is one of {VERDICTS}")
        with self._lock:
            self._match(portfolio_id)
            matched = self._con.execute(
                "select record_id from portfolio_match where member_id = ? and entity_id = ?", [member_id, entity_id]
            ).fetchall()
            if not matched:
                raise LookupError(f"member {member_id} has no Match to {entity_id}")
            parameters = {"portfolio": portfolio_id, "member": member_id, "entity": entity_id}
            self._con.begin()
            self._con.execute(REPLACED_VERDICT_SQL, parameters)
            self._con.execute(
                "insert into workspace.verdict values ($portfolio, $member, $record, $verdict, now())",
                {"portfolio": portfolio_id, "member": member_id, "record": matched[0][0], "verdict": verdict},
            )
            self._con.commit()

    def exposure(self, portfolio_id: str) -> Exposure:
        """Hidden Concentrations ranked by share of the Portfolio, and how much of its ownership is unverifiable."""
        with self._lock:
            total = self._match(portfolio_id)
            self._con.execute(MEMBER_ENTITY_SQL)
            groups = self._rows(CONCENTRATION_SQL, {"total": total, "kinds": CAUSE_KINDS, "last_kind": LAST_CAUSE_KIND})
            members: dict[tuple[str, str], list[ConcentrationMember]] = {}
            for row in self._rows(CONCENTRATION_MEMBER_SQL, {"portfolio": portfolio_id}):
                path = [PathStep(**step) for step in row.pop("path")]
                members.setdefault((row.pop("kind"), row.pop("key")), []).append(ConcentrationMember(**row, path=path))
            ownership = [
                MemberOwnership(**row) for row in self._rows(MEMBER_OWNERSHIP_SQL, {"portfolio": portfolio_id})
            ]
            disagreements = [
                Disagreement(*row)
                for row in self._con.execute(DISAGREEMENT_SQL, {"portfolio": portfolio_id}).fetchall()
            ]
            as_of = dict(self._con.execute(AS_OF_SQL).fetchall())
        return Exposure(
            portfolio_id=portfolio_id,
            members=total,
            concentrations=[Concentration(**g, members=members[(g["kind"], g["key"])]) for g in groups],
            ownership=Ownership(
                total=total,
                matched=sum(m.status is not None for m in ownership),
                unmatched=sum(m.status is None for m in ownership),
                unverifiable=sum(m.status == "Undisclosed Parent" for m in ownership),
                members=ownership,
                disagreements=disagreements,
            ),
            as_of=as_of,
        )

    def _match(self, portfolio_id: str) -> int:
        """Matches the Portfolio's members into `portfolio_match`; returns how many members it has."""
        total = self._con.execute(
            "select count(*) from workspace.portfolio_member where portfolio_id = ?", [portfolio_id]
        ).fetchall()[0][0]
        if not total:
            raise LookupError(f"no Portfolio {portfolio_id}")
        self._con.execute(
            PORTFOLIO_MATCH_SQL,
            {"portfolio": portfolio_id, "possible": POSSIBLE_NAME_SCORE, "max_possible": MAX_POSSIBLE_MATCHES},
        )
        return total

    def _rows(self, sql: str, parameters: Any = None) -> list[dict[str, Any]]:
        cursor = self._con.execute(sql, parameters)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _sql_string(path: Path) -> str:
    return str(path).replace("'", "''")
