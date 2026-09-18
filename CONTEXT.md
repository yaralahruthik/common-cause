# Supply Chain Entity and Risk Graph

A graph of real-world companies inferred from public registries, used by a procurement team to find exposure that is hidden behind apparently independent suppliers and carriers.

## Language

### Who is in the graph

**Entity**:
One real-world company, regardless of how many source records describe it.
_Avoid_: Company record, node, organisation

**Source Record**:
One row from one public registry, kept exactly as published. Many Source Records may describe one Entity.
_Avoid_: Raw entity, row, listing

**Carrier**:
An Entity that holds one or more Registrations, whether it hauls for hire or runs a private fleet for its own goods. A Supplier can also be a Carrier.
_Avoid_: Trucker, transporter, operator, trucking company

**Registration**:
One operating authority record held by a Carrier, identified by its own registry number. Its status is a fact about the Registration, not about the Entity that holds it.
_Avoid_: USDOT record, licence, carrier record

**Supplier**:
An Entity that provides goods or materials to the Portfolio's owner. A Supplier is known only because the user said so; no source in this system evidences a supply relationship.
_Avoid_: Vendor, partner

**Agent Address**:
An address shared by so many unrelated Entities that it identifies a registered agent, virtual office or mail drop rather than a place of operation. It is neither evidence for a Match nor a Common Cause.
_Avoid_: Shared address, PO box, registered office

### How they connect

**Ownership Link**:
A directed, registry-evidenced relationship in which one Entity consolidates another in its accounts. It is not a Supply Link.
_Avoid_: Parent edge, supplier-of, upstream

**Ownership Status**:
What is known about who owns an Entity: Declared Parent, Declared Independent, or Undisclosed Parent. The absence of an Ownership Link is never read as independence.
_Avoid_: Has parent, orphan, standalone

**Declared Parent**:
The Entity's registry entry names the Entity that consolidates it.

**Declared Independent**:
The Entity's registry entry states that no corporate parent exists, for example because it is owned by natural persons.

**Undisclosed Parent**:
A parent exists but is withheld or unidentifiable, or nothing about ownership is known at all. Independence cannot be verified.
_Avoid_: No parent, unknown, missing

**Supply Link**:
A commercial relationship in which one Entity provides goods to another. Asserted by the user for their own Portfolio; never inferred from an Ownership Link.
_Avoid_: Tier edge, dependency

**Ultimate Parent**:
The Entity at the top of a chain of Ownership Links.
_Avoid_: Root, group, holding

**Declared Ultimate Parent**:
The Entity a registry entry names directly as its top-level consolidator. It may disagree with the Ultimate Parent reached by walking Ownership Links, and the disagreement is itself a finding.
_Avoid_: Filed parent, GLEIF ultimate

**Tier**:
Distance from the Portfolio's owner measured in Supply Links only. Hops along Ownership Links are not Tiers.
_Avoid_: Level, depth, hop

### What the user does

**Portfolio**:
The list of Supplier and Carrier names a procurement user brings to the system as their known direct relationships.
_Avoid_: Supplier list, watchlist, upload

**Match**:
A proposed pairing of a Portfolio name, or of two Source Records, to one Entity, carrying a confidence and the evidence behind it.
_Avoid_: Merge, dedupe, link

**Firm Match**:
A Match strong enough that the system asserts it without asking.
_Avoid_: Auto-merge, exact match

**Possible Match**:
A Match too weak to assert and too strong to discard; shown to the analyst as unconfirmed until they confirm or reject it.
_Avoid_: Fuzzy match, maybe, candidate

**Verdict**:
An analyst's confirmation or rejection of a Match, which holds for their Portfolio only.
_Avoid_: Override, feedback, label

**Hidden Concentration**:
Two or more Portfolio members that appear independent but share a Common Cause.
_Avoid_: Single point of failure, overlap, cluster

**Common Cause**:
The thing Portfolio members share that would fail them together: one Ultimate Parent, one physical address, or one jurisdiction.
_Avoid_: Risk factor, link type

**Tentative Concentration**:
A Hidden Concentration that holds only if at least one Possible Match is true.
_Avoid_: Low-confidence finding, weak cluster

**As-Of Date**:
The publication date of the source that a fact was taken from; the limit of how current that fact can be.
_Avoid_: Last updated, timestamp, freshness

**Staleness**:
The condition of a Source Record whose registry marks it lapsed, inactive, or long un-refreshed. Shown as a risk signal, never cleaned away.
_Avoid_: Bad data, outdated

### How resolution is checked

**Labelled Pair**:
A Match drawn into a fixed sample and judged same Entity, different, or unsure, so that precision can be measured per band. Its label belongs to no Portfolio and changes no Match; that is what separates it from a Verdict.
_Avoid_: Verdict, ground truth, gold pair
