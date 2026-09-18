// The API's shapes (src/common_cause/api and src/common_cause/exposure/graph.py) and calls to it.

export interface MemberIn {
  name: string;
  state: string | null;
  city: string | null;
}

export type Band = "Firm" | "Possible";
export type Verdict = "confirmed" | "rejected";

export interface Match {
  entity_id: string;
  band: Band;
  score: number;
  record_id: string;
  name: string;
  city: string | null;
  state: string | null;
  evidence: string;
  verdict: Verdict | null;
  entity_records: string[];
}

export interface PortfolioMember extends MemberIn {
  member_id: number;
  matches: Match[];
}

export interface Portfolio {
  portfolio_id: string;
  sample: boolean;
  members: PortfolioMember[];
}

export interface PathStep {
  lei: string;
  name: string | null;
  jurisdiction: string | null;
}

export interface ConcentrationMember {
  member_id: number;
  name: string;
  entity_id: string;
  firm: boolean;
  path: PathStep[];
  basis: string | null;
  declared_ultimate_parent_lei: string | null;
}

export type CauseKind = "Ultimate Parent" | "Address" | "Jurisdiction";

export interface Concentration {
  id: string;
  kind: CauseKind;
  key: string;
  label: string;
  share: number;
  share_if_possible_matches_hold: number;
  tentative: boolean;
  members: ConcentrationMember[];
}

export type OwnershipStatus = "Declared Parent" | "Declared Independent" | "Undisclosed Parent";

export interface MemberOwnership {
  member_id: number;
  name: string;
  status: OwnershipStatus | null;
  basis: string;
}

export interface Exposure {
  portfolio_id: string;
  members: number;
  affected: number;
  affected_if_possible_matches_hold: number;
  concentrations: Concentration[];
  ownership: {
    total: number;
    matched: number;
    unmatched: number;
    unverifiable: number;
    members: MemberOwnership[];
    disagreements: { member_id: number; name: string; lei: string; walked_lei: string; declared_lei: string }[];
  };
  as_of: Record<string, string | null>;
}

export interface OutOfServiceOrder {
  ordered: string | null;
  reason: string | null;
  status: string | null;
  rescinded: string | null;
}

export interface Registration {
  dot_number: string;
  name: string;
  dba_name: string | null;
  status: string | null;
  power_units: number | null;
  street: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  last_filed: string | null;
  out_of_service: OutOfServiceOrder[];
}

export interface DetailMember {
  member_id: number;
  name: string;
  entity_id: string;
  firm: boolean;
  match: Match;
  alternatives: Match[];
  ownership_status: OwnershipStatus | null;
  ownership_basis: string;
  leis: string[];
  path: PathStep[];
  basis: string | null;
  declared_ultimate_parent_lei: string | null;
  registrations: Registration[];
}

export interface Site {
  street: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  names_registered: number;
  agent_threshold: number;
  others: { name: string; record_ids: string[] }[];
}

export interface ConcentrationDetail {
  id: string;
  kind: CauseKind;
  key: string;
  label: string;
  total: number;
  share: number;
  share_if_possible_matches_hold: number;
  tentative: boolean;
  rank: number;
  ranked: number;
  members: DetailMember[];
  site: Site | null;
  as_of: Record<string, string | null>;
}

export interface Sample {
  description: string;
  members: MemberIn[];
  baseline: {
    description: string;
    members: MemberIn[];
    matched: number;
    unverifiable: number;
    concentrations: number;
    affected: number;
  };
}

export class NotFound extends Error {}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 404) throw new NotFound(path);
  if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${await response.text()}`);
  return (await response.json()) as T;
}

const portfolioPath = (id: string) => `/portfolios/${encodeURIComponent(id)}`;
const verdictPath = (id: string, memberId: number, entityId: string) =>
  `${portfolioPath(id)}/members/${memberId}/verdicts/${encodeURIComponent(entityId)}`;

export const api = {
  sample: () => call<Sample>("GET", "/sample"),
  createPortfolio: (members: MemberIn[], sample = false) =>
    call<Portfolio>("POST", "/portfolios", { members, sample }),
  portfolio: (id: string) => call<Portfolio>("GET", portfolioPath(id)),
  updateMember: (id: string, memberId: number, member: MemberIn) =>
    call<PortfolioMember>("PUT", `${portfolioPath(id)}/members/${memberId}`, member),
  recordVerdict: (id: string, memberId: number, entityId: string, verdict: Verdict) =>
    call<PortfolioMember>("PUT", verdictPath(id, memberId, entityId), { verdict }),
  clearVerdict: (id: string, memberId: number, entityId: string) =>
    call<PortfolioMember>("DELETE", verdictPath(id, memberId, entityId)),
  exposure: (id: string) => call<Exposure>("GET", `${portfolioPath(id)}/exposure`),
  concentration: (id: string, concentrationId: string) =>
    call<ConcentrationDetail>("GET", `${portfolioPath(id)}/concentrations/${encodeURIComponent(concentrationId)}`),
};
