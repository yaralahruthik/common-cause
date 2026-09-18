import type { ConcentrationMember, DetailMember, Exposure, Match, PathStep, PortfolioMember } from "./api";

export function match(entity_id: string, band: Match["band"], verdict: Match["verdict"] = null): Match {
  return {
    entity_id,
    band,
    score: 1,
    record_id: entity_id,
    name: entity_id.toUpperCase(),
    city: null,
    state: null,
    evidence: "",
    verdict,
    entity_records: [entity_id],
  };
}

export function member(member_id: number, name: string, matches: Match[]): PortfolioMember {
  return { member_id, name, state: null, city: null, matches };
}

export function step(lei: string): PathStep {
  return { lei, name: lei, jurisdiction: null };
}

export function concentrationMember(
  member_id: number,
  name: string,
  firm = true,
  path: string[] = [],
): ConcentrationMember {
  return {
    member_id,
    name,
    entity_id: `e${member_id}`,
    firm,
    path: path.map(step),
    basis: path.length ? "walked" : null,
    declared_ultimate_parent_lei: null,
  };
}

export function detailMember(member_id: number, firm: boolean, path: string[], basis = "walked"): DetailMember {
  return {
    ...concentrationMember(member_id, `Member ${member_id}`, firm, path),
    basis,
    match: match(`e${member_id}`, firm ? "Firm" : "Possible"),
    alternatives: [],
    ownership_status: "Declared Parent",
    ownership_basis: "",
    leis: [path[0] ?? ""],
    registrations: [],
  };
}

export function exposure(overrides: Partial<Exposure>): Exposure {
  return {
    portfolio_id: "p",
    members: 15,
    affected: 0,
    affected_if_possible_matches_hold: 0,
    concentrations: [],
    ownership: { total: 15, matched: 13, unmatched: 2, unverifiable: 5, members: [], disagreements: [] },
    as_of: {},
    ...overrides,
  };
}
