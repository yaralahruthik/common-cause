"""Turns downloaded registry files into the committed Parquet snapshot.

Everything here reads local files only; fetching lives in `fetch.py`.
"""

import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.csv as pacsv

# GLEIF Level 1 columns kept, published name -> snapshot name. Values are kept as published.
LEVEL1_COLUMNS = {
    "LEI": "lei",
    "Entity.LegalName": "legal_name",
    "Entity.OtherEntityNames.OtherEntityName.1": "other_name_1",
    "Entity.OtherEntityNames.OtherEntityName.1.type": "other_name_1_type",
    "Entity.OtherEntityNames.OtherEntityName.2": "other_name_2",
    "Entity.OtherEntityNames.OtherEntityName.2.type": "other_name_2_type",
    "Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName.1": "transliterated_name_1",
    "Entity.LegalAddress.FirstAddressLine": "legal_address_line_1",
    "Entity.LegalAddress.AdditionalAddressLine.1": "legal_address_line_2",
    "Entity.LegalAddress.City": "legal_city",
    "Entity.LegalAddress.Region": "legal_region",
    "Entity.LegalAddress.Country": "legal_country",
    "Entity.LegalAddress.PostalCode": "legal_postal_code",
    "Entity.HeadquartersAddress.FirstAddressLine": "hq_address_line_1",
    "Entity.HeadquartersAddress.AdditionalAddressLine.1": "hq_address_line_2",
    "Entity.HeadquartersAddress.City": "hq_city",
    "Entity.HeadquartersAddress.Region": "hq_region",
    "Entity.HeadquartersAddress.Country": "hq_country",
    "Entity.HeadquartersAddress.PostalCode": "hq_postal_code",
    "Entity.RegistrationAuthority.RegistrationAuthorityID": "registration_authority_id",
    "Entity.RegistrationAuthority.RegistrationAuthorityEntityID": "registration_authority_entity_id",
    "Entity.LegalJurisdiction": "legal_jurisdiction",
    "Entity.EntityCategory": "entity_category",
    "Entity.LegalForm.EntityLegalFormCode": "legal_form_code",
    "Entity.LegalForm.OtherLegalForm": "other_legal_form",
    "Entity.EntityStatus": "entity_status",
    "Entity.EntityCreationDate": "entity_creation_date",
    "Entity.EntityExpirationDate": "entity_expiration_date",
    "Entity.EntityExpirationReason": "entity_expiration_reason",
    "Entity.SuccessorEntity.1.SuccessorLEI": "successor_lei",
    "Registration.InitialRegistrationDate": "initial_registration_date",
    "Registration.LastUpdateDate": "last_update_date",
    "Registration.RegistrationStatus": "registration_status",
    "Registration.NextRenewalDate": "next_renewal_date",
    "Registration.ManagingLOU": "managing_lou",
    "Registration.ValidationSources": "validation_sources",
}

# GLEIF Level 2 relationship columns kept. StartNode is the child, EndNode the parent.
RELATIONSHIP_COLUMNS = {
    "Relationship.StartNode.NodeID": "child_lei",
    "Relationship.EndNode.NodeID": "parent_lei",
    "Relationship.RelationshipType": "relationship_type",
    "Relationship.RelationshipStatus": "relationship_status",
    "Relationship.Period.1.startDate": "relationship_start_date",
    "Registration.InitialRegistrationDate": "initial_registration_date",
    "Registration.LastUpdateDate": "last_update_date",
    "Registration.RegistrationStatus": "registration_status",
    "Registration.ValidationSources": "validation_sources",
}

# Fund, sub-fund, feeder and branch relationships are not ownership and are skipped.
CONSOLIDATION_TYPES = ("IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY")

# GLEIF reporting exception columns kept: why a record names no parent in place of an edge.
EXCEPTION_COLUMNS = {
    "LEI": "lei",
    "Exception.Category": "exception_category",
    **{f"Exception.Reason.{n}": f"exception_reason_{n}" for n in range(1, 6)},
    **{f"Exception.Reference.{n}": f"exception_reference_{n}" for n in range(1, 6)},
}

# Exception reasons that state no corporate parent exists. Every other reason means one is withheld,
# and an exception giving several reasons is independent only if all of them say so.
INDEPENDENT_REASONS = ("NATURAL_PERSONS", "NON_CONSOLIDATING")

# One row per kept LEI record. An active consolidation edge wins; otherwise the direct-parent exception,
# falling back to the ultimate-parent one; otherwise nothing is known and independence is unverifiable.
OWNERSHIP_STATUS_SQL = """
create table gleif_ownership_status as
with declared_parent as (
    select child_lei as lei, min(relationship_type) as relationship_type
    from gleif_ownership_link
    where relationship_status = 'ACTIVE'
    group by child_lei
),
exception as (
    -- DIRECT_... sorts before ULTIMATE_..., so arg_min prefers the direct-parent exception.
    select
        lei,
        arg_min(
            list_filter(
                [exception_reason_1, exception_reason_2, exception_reason_3, exception_reason_4, exception_reason_5],
                reason -> reason <> ''
            ),
            exception_category
        ) as reasons
    from gleif_reporting_exception
    group by lei
)
select
    record.lei,
    case
        when declared_parent.lei is not null then 'Declared Parent'
        when len(exception.reasons) > 0 and list_has_all($independent, exception.reasons)
            then 'Declared Independent'
        else 'Undisclosed Parent'
    end as ownership_status,
    case
        when declared_parent.lei is not null then declared_parent.relationship_type
        when len(exception.reasons) > 0 then 'exception: ' || array_to_string(exception.reasons, ', ')
        else 'no ownership filing'
    end as ownership_basis
from gleif_record as record
left join declared_parent using (lei)
left join exception using (lei)
"""


# FMCSA census slice: fleets of this many power units or more, in any status.
MIN_POWER_UNITS = 10


@dataclass(frozen=True)
class RawSources:
    gleif_level1: Path
    gleif_relationships: Path
    gleif_exceptions: Path
    gleif_as_of: date
    fmcsa_census: Path
    fmcsa_census_as_of: date
    fmcsa_oos: Path
    fmcsa_oos_as_of: date


@contextmanager
def _zipped_csv(path: Path, columns: dict[str, str]) -> Iterator[pa.RecordBatchReader]:
    """Streams only `columns` out of the single CSV inside a GLEIF zip, renamed, all as text."""
    with zipfile.ZipFile(path) as archive, archive.open(archive.namelist()[0]) as member:
        reader = pacsv.open_csv(
            member,
            read_options=pacsv.ReadOptions(block_size=64 << 20),
            parse_options=pacsv.ParseOptions(newlines_in_values=True),
            convert_options=pacsv.ConvertOptions(
                include_columns=list(columns),
                column_types={name: pa.string() for name in columns},
                strings_can_be_null=False,
            ),
        )
        renamed = reader.schema.names
        yield pa.RecordBatchReader.from_batches(
            pa.schema([pa.field(columns[name], pa.string()) for name in renamed]),
            (batch.rename_columns([columns[name] for name in renamed]) for batch in reader),
        )


@dataclass(frozen=True)
class BuildReport:
    table_rows: dict[str, int]
    # Every relationship type in the full GLEIF Level 2 file, including the ones the slice skips.
    relationship_types: dict[str, int]


def build_snapshot(raw: RawSources, out_dir: Path) -> BuildReport:
    """Writes one Parquet file per table into `out_dir`."""
    con = duckdb.connect()
    relationship_types = _load_gleif(con, raw)
    _load_fmcsa(con, raw)

    as_of = {
        "gleif_record": raw.gleif_as_of,
        "gleif_ownership_link": raw.gleif_as_of,
        "gleif_reporting_exception": raw.gleif_as_of,
        "gleif_ownership_status": raw.gleif_as_of,
        "fmcsa_census": raw.fmcsa_census_as_of,
        "fmcsa_oos_order": raw.fmcsa_oos_as_of,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    # Every Parquet file in the directory is loaded as a table, so files from an older build must go.
    for stale in out_dir.glob("*.parquet"):
        stale.unlink()
    table_rows: dict[str, int] = {}
    for table, as_of_date in as_of.items():
        path = out_dir / f"{table}.parquet"
        con.execute(
            f"copy (select *, ?::date as as_of_date from {table}) to '{path}' (format parquet, compression zstd)",
            [as_of_date],
        )
        table_rows[table] = con.execute(f"select count(*) from {table}").fetchall()[0][0]
    return BuildReport(table_rows, relationship_types)


def _load_gleif(con: duckdb.DuckDBPyConnection, raw: RawSources) -> dict[str, int]:
    """Loads the GLEIF tables and returns the full-file count per relationship type."""
    with _zipped_csv(raw.gleif_relationships, RELATIONSHIP_COLUMNS) as relationships:
        con.register("relationships", relationships)
        con.execute("create temp table all_relationships as select * from relationships")
    con.execute(
        "create table gleif_ownership_link as select * from all_relationships where relationship_type in ?",
        [list(CONSOLIDATION_TYPES)],
    )
    relationship_types = dict(
        con.execute(
            "select relationship_type, count(*) from all_relationships group by all order by count(*) desc"
        ).fetchall()
    )
    with _zipped_csv(raw.gleif_level1, LEVEL1_COLUMNS) as level1:
        con.register("level1", level1)
        con.execute(
            """
            create table gleif_record as
            select * from level1
            where legal_country = 'US' or hq_country = 'US'
               or lei in (select child_lei from gleif_ownership_link)
               or lei in (select parent_lei from gleif_ownership_link)
            """
        )
    with _zipped_csv(raw.gleif_exceptions, EXCEPTION_COLUMNS) as exceptions:
        con.register("exceptions", exceptions)
        con.execute(
            """
            create table gleif_reporting_exception as
            select * from exceptions where lei in (select lei from gleif_record)
            """
        )
    con.execute(OWNERSHIP_STATUS_SQL, {"independent": list(INDEPENDENT_REASONS)})
    return relationship_types


def _load_fmcsa(con: duckdb.DuckDBPyConnection, raw: RawSources) -> None:
    con.execute(
        f"""
        create table fmcsa_census as
        select * from read_csv(?, header = true, all_varchar = true)
        where try_cast(power_units as double) >= {MIN_POWER_UNITS}
        """,
        [str(raw.fmcsa_census)],
    )
    con.execute(
        """
        create table fmcsa_oos_order as
        select * from read_csv(?, header = true, all_varchar = true)
        where dot_number in (select dot_number from fmcsa_census)
        """,
        [str(raw.fmcsa_oos)],
    )
