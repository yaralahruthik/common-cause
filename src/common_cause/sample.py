"""The sample Portfolio offered to someone with no list at hand, and the random Portfolio shown beside it.

The sample is curated: 15 food and beverage makers that run their own trucks, which is what puts them in the FMCSA
census, chosen because their records are in the snapshot. A curated list finds what it was chosen to find, so the
interface reports a random Portfolio's result next to it.
"""

from common_cause.exposure.graph import Member

SAMPLE_MEMBERS = [
    Member("Rolling Frito-Lay Sales LP", "TX"),
    Member("Naked Juice LLC"),
    Member("Prairie Farms Dairy", "IL"),
    Member("Hiland Dairy Foods Company LLC"),
    Member("East Side Jersey Dairy", "IL"),
    Member("Mrs Stratton's Salads"),
    Member("Star Food Products Inc"),
    Member("Nestle Purina PetCare Company", "MO"),
    Member("Nestle USA Inc"),
    Member("Bar-S Foods Co"),
    Member("Koch Foods LLC", "TN"),
    Member("Herr Foods Inc", "PA", "NOTTINGHAM"),
    Member("Coca-Cola Bottling Company United"),
    Member("Saputo Cheese USA Inc"),
    Member("Bimbo Bakeries USA Inc"),
]

SAMPLE_DESCRIPTION = (
    "15 food and beverage makers that run their own trucks. Curated: chosen because their records are in the data."
)

# Drawn once, with seed 20260918, from active FMCSA Registrations whose classdef includes PRIVATE PROPERTY (companies
# running trucks for their own goods), each given as its legal name and state. Fixed here so the comparison does not
# change between runs.
BASELINE_MEMBERS = [
    Member("WILLIAM DICKSON INDUSTRIES INC", "PA"),
    Member("GRACIOUS HOME LLC", "NY"),
    Member("PITT OIL SERVICE INC", "PA"),
    Member("KINZER DRILLING COMPANY LLC", "KY"),
    Member("CHOATES AIRCONDITIONING HEATING & PLUMBING", "TN"),
    Member("SE CONSTRUCTION CORPORATION", "GU"),
    Member("THE VONS COMPANIES INC", "CA"),
    Member("LAKESHORE DISPOSAL INC", "MI"),
    Member("COOK BROTHERS EXCAVATING INC", "MI"),
    Member("SPIERS CONSTRUCTION LLC", "ID"),
    Member("R L CRAFT CO INC", "IA"),
    Member("NY HOME MAINTENANCE CO INC", "NY"),
    Member("WASTE MANAGEMENT OF MISSISSIPPI INC", "MS"),
    Member("DELTA LIQUID ENERGY HOLDINGS LLC", "CA"),
    Member("QUICK DROP INDUSTRIES LLC", "NY"),
]

BASELINE_DESCRIPTION = "15 companies drawn at random from the active FMCSA Registrations that run a private fleet."
