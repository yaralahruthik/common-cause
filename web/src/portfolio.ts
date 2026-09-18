import type { Match, PortfolioMember } from "./api";

export interface Matched {
  member: PortfolioMember;
  match: Match;
}

export interface Undecided {
  member: PortfolioMember;
  candidates: Match[];
}

export interface NotFound {
  member: PortfolioMember;
  rejected: Match[];
}

/** The three groups of the Portfolio screen, following the API's rules for which Match stands (graph.py
 *  MEMBER_ENTITY_SQL): a Firm or confirmed Match stands; otherwise the unjudged Possible Matches wait for a Verdict;
 *  a member with neither is not found. */
export function groupMembers(members: PortfolioMember[]): {
  matched: Matched[];
  decide: Undecided[];
  notFound: NotFound[];
} {
  const matched: Matched[] = [];
  const decide: Undecided[] = [];
  const notFound: NotFound[] = [];
  for (const member of members) {
    const standing =
      member.matches.find((m) => m.verdict === "confirmed") ??
      member.matches.find((m) => m.band === "Firm" && m.verdict !== "rejected");
    const candidates = member.matches.filter((m) => m.band === "Possible" && m.verdict === null);
    if (standing) matched.push({ member, match: standing });
    else if (candidates.length) decide.push({ member, candidates });
    else notFound.push({ member, rejected: member.matches.filter((m) => m.verdict === "rejected") });
  }
  return { matched, decide, notFound };
}

/** A Source Record by the registry's own id: `USDOT 926150`, `LEI 5493…`. */
export function recordLabel(recordId: string): string {
  const [source, id] = recordId.split(":", 2);
  return source === "fmcsa" ? `USDOT ${id}` : source === "gleif" ? `LEI ${id}` : recordId;
}

export function recordSource(recordId: string): string {
  return recordId.startsWith("fmcsa:") ? "FMCSA" : "GLEIF";
}

/** Where a registry's own page for the record is. */
export function recordUrl(recordId: string): string {
  const [source, id] = recordId.split(":", 2);
  return source === "fmcsa" ? dotUrl(id ?? "") : leiUrl(id ?? "");
}

export function dotUrl(dotNumber: string): string {
  return (
    "https://safer.fmcsa.dot.gov/query.asp?searchtype=ANY&query_type=queryCarrierSnapshot&query_param=USDOT" +
    `&query_string=${encodeURIComponent(dotNumber)}`
  );
}

export function leiUrl(lei: string): string {
  return `https://search.gleif.org/#/record/${encodeURIComponent(lei)}`;
}

export function place(city: string | null, state: string | null): string {
  return [city, state].filter(Boolean).join(", ");
}
