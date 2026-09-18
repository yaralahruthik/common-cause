"""Builds tiny raw source files shaped like the real registry downloads."""

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from common_cause.ingest.build import RawSources

LEVEL1_HEADER = [
    "LEI",
    "Entity.LegalName",
    "Entity.LegalName.xmllang",
    *(
        f"Entity.OtherEntityNames.OtherEntityName.{n}{suffix}"
        for n in range(1, 3)
        for suffix in ("", ".xmllang", ".type")
    ),
    "Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName.1",
    *(
        f"Entity.{kind}.{part}"
        for kind in ("LegalAddress", "HeadquartersAddress")
        for part in ("FirstAddressLine", "AdditionalAddressLine.1", "City", "Region", "Country", "PostalCode")
    ),
    "Entity.RegistrationAuthority.RegistrationAuthorityID",
    "Entity.RegistrationAuthority.RegistrationAuthorityEntityID",
    "Entity.LegalJurisdiction",
    "Entity.EntityCategory",
    "Entity.LegalForm.EntityLegalFormCode",
    "Entity.LegalForm.OtherLegalForm",
    "Entity.EntityStatus",
    "Entity.EntityCreationDate",
    "Entity.EntityExpirationDate",
    "Entity.EntityExpirationReason",
    "Entity.SuccessorEntity.1.SuccessorLEI",
    "Registration.InitialRegistrationDate",
    "Registration.LastUpdateDate",
    "Registration.RegistrationStatus",
    "Registration.NextRenewalDate",
    "Registration.ManagingLOU",
    "Registration.ValidationSources",
    "ConformityFlag",
]

RR_HEADER = [
    "Relationship.StartNode.NodeID",
    "Relationship.StartNode.NodeIDType",
    "Relationship.EndNode.NodeID",
    "Relationship.EndNode.NodeIDType",
    "Relationship.RelationshipType",
    "Relationship.RelationshipStatus",
    "Relationship.Period.1.startDate",
    "Registration.InitialRegistrationDate",
    "Registration.LastUpdateDate",
    "Registration.RegistrationStatus",
    "Registration.ValidationSources",
]

REPEX_HEADER = [
    "LEI",
    "Exception.Category",
    *(f"Exception.Reason.{n}" for n in range(1, 6)),
    *(f"Exception.Reference.{n}" for n in range(1, 6)),
]

CENSUS_HEADER = [
    "dot_number",
    "legal_name",
    "dba_name",
    "status_code",
    "power_units",
    "phy_street",
    "phy_city",
    "phy_state",
    "phy_zip",
    "phone",
    "company_officer_1",
    "company_officer_2",
    "prior_revoke_dot_number",
]

OOS_HEADER = ["dot_number", "legal_name", "dba_name", "oos_date", "oos_reason", "status", "rescind_date"]


def _csv_text(header: list[str], rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, quoting=csv.QUOTE_ALL, restval="")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _write_zip(path: Path, header: list[str], rows: list[dict[str, str]]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(path.name.removesuffix(".zip"), _csv_text(header, rows))
    return path


@dataclass
class RawSourceBuilder:
    """Collects rows per source, then writes them the way the registries publish them."""

    level1: list[dict[str, str]] = field(default_factory=list)
    relationships: list[dict[str, str]] = field(default_factory=list)
    exceptions: list[dict[str, str]] = field(default_factory=list)
    census: list[dict[str, str]] = field(default_factory=list)
    oos: list[dict[str, str]] = field(default_factory=list)
    gleif_as_of: date = date(2026, 9, 18)
    census_as_of: date = date(2026, 9, 14)
    oos_as_of: date = date(2026, 9, 17)

    def lei_record(self, lei: str, name: str, legal_country: str = "US", hq_country: str = "US", **extra: str) -> None:
        self.level1.append(
            {
                "LEI": lei,
                "Entity.LegalName": name,
                "Entity.LegalAddress.Country": legal_country,
                "Entity.HeadquartersAddress.Country": hq_country,
                "Entity.EntityStatus": "ACTIVE",
                "Registration.RegistrationStatus": "ISSUED",
                **extra,
            }
        )

    def relationship(self, child: str, parent: str, kind: str, status: str = "ACTIVE") -> None:
        self.relationships.append(
            {
                "Relationship.StartNode.NodeID": child,
                "Relationship.StartNode.NodeIDType": "LEI",
                "Relationship.EndNode.NodeID": parent,
                "Relationship.EndNode.NodeIDType": "LEI",
                "Relationship.RelationshipType": kind,
                "Relationship.RelationshipStatus": status,
                "Registration.RegistrationStatus": "PUBLISHED",
            }
        )

    def exception(self, lei: str, *reasons: str, category: str = "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT") -> None:
        row = {"LEI": lei, "Exception.Category": category}
        row.update({f"Exception.Reason.{n}": reason for n, reason in enumerate(reasons, start=1)})
        self.exceptions.append(row)

    def registration(self, dot_number: str, name: str, power_units: str = "12", **extra: str) -> None:
        self.census.append({"dot_number": dot_number, "legal_name": name, "power_units": power_units, **extra})

    def oos_order(self, dot_number: str, oos_date: str, reason: str = "Unsatisfactory = Unfit") -> None:
        self.oos.append({"dot_number": dot_number, "oos_date": oos_date, "oos_reason": reason, "status": "ACTIVE"})

    def write(self, directory: Path) -> RawSources:
        census_path = directory / "census.csv"
        census_path.write_text(_csv_text(CENSUS_HEADER, self.census))
        oos_path = directory / "oos.csv"
        oos_path.write_text(_csv_text(OOS_HEADER, self.oos))
        return RawSources(
            gleif_level1=_write_zip(directory / "lei2.csv.zip", LEVEL1_HEADER, self.level1),
            gleif_relationships=_write_zip(directory / "rr.csv.zip", RR_HEADER, self.relationships),
            gleif_exceptions=_write_zip(directory / "repex.csv.zip", REPEX_HEADER, self.exceptions),
            gleif_as_of=self.gleif_as_of,
            fmcsa_census=census_path,
            fmcsa_census_as_of=self.census_as_of,
            fmcsa_oos=oos_path,
            fmcsa_oos_as_of=self.oos_as_of,
        )
