import type { Concentration, Exposure, Sample } from "./api";

export function memberCount(share: number, total: number): number {
  return Math.round(share * total);
}

/** Concentrations in the API's ranked order, shared jurisdictions set apart: ranked with the rest, a common state
 *  of incorporation would nearly always come first and tell the analyst least. */
export function rankedConcentrations(exposure: Exposure): { ranked: Concentration[]; jurisdictions: Concentration[] } {
  return {
    ranked: exposure.concentrations.filter((c) => c.kind !== "Jurisdiction"),
    jurisdictions: exposure.concentrations.filter((c) => c.kind === "Jurisdiction"),
  };
}

/** The one sentence for the CPO. It counts firm findings only. */
export function sentence(exposure: Exposure): string {
  const { affected, members } = exposure;
  const { matched, unverifiable } = exposure.ownership;
  const sharing =
    affected === 0
      ? `None of your ${members} suppliers shares`
      : affected === 1
        ? `1 of your ${members} suppliers shares`
        : `${affected} of your ${members} suppliers share`;
  const owners =
    matched === 0
      ? "and we have not yet matched any of them to a registry record"
      : unverifiable === 0
        ? `and every one of the ${matched} we matched names its owner or declares it has none`
        : `and we cannot see who owns ${unverifiable} of the ${matched} we matched`;
  return `${sharing} an owner or a site with another supplier on this list, ${owners}.`;
}

/** Why concentrations of equal size come in the order they do, when any do. */
export function tieNote(ranked: Concentration[], total: number): string | null {
  const counts = ranked.map((c) => memberCount(c.share, total));
  if (counts.length > 1 && counts.every((n) => n === counts[0])) {
    return `Each is ${counts[0]} of ${total}, so ties are ordered by kind of Common Cause`;
  }
  return new Set(counts).size < counts.length ? "Equal sizes are ordered by kind of Common Cause" : null;
}

/** The members whose unconfirmed Matches the given concentrations rest on. */
export function undecidedNames(concentrations: Concentration[]): string[] {
  return [...new Set(concentrations.flatMap((c) => c.members.filter((m) => !m.firm).map((m) => m.name)))];
}

export function causeName(kind: Concentration["kind"]): string {
  return kind === "Ultimate Parent" ? "Shared Ultimate Parent" : kind === "Address" ? "Shared physical address" : "Shared jurisdiction";
}

/** "A", "A and B", "A, B and C". */
export function listNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** What the random Portfolio shown beside the sample finds, in the same terms as the sample's own figures. */
export function baselineSummary(baseline: Sample["baseline"]): string {
  const list = `a random list of ${baseline.members.length} fleets from the same data`;
  if (baseline.concentrations === 0) return `${list} finds no Hidden Concentrations`;
  const found = `${baseline.concentrations} Hidden ${baseline.concentrations === 1 ? "Concentration" : "Concentrations"}`;
  return `${list} finds ${found}, with ${baseline.affected} of its members firmly in one`;
}
