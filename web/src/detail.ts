import type { ConcentrationDetail, DetailMember } from "./api";
import { listNames } from "./exposure";

function titleCase(text: string): string {
  return text.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Closes a sentence, unless it already ends on an abbreviation's full stop ("NESTLÉ S.A."). */
function stop(text: string): string {
  return text.endsWith(".") ? text : `${text}.`;
}

function both(count: number): string {
  return count === 2 ? "both" : "all";
}

/** The detail screen's one-line finding. */
export function detailHeading(detail: ConcentrationDetail): string {
  const { members, tentative } = detail;
  const names = listNames(members.map((m) => m.name));
  if (detail.kind === "Ultimate Parent") {
    const owner = members.find((m) => m.path.length === 1);
    if (owner) {
      const owned = members.filter((m) => m !== owner);
      const verb = owned.length === 1 ? (tentative ? "may be" : "is") : tentative ? "may be" : "are";
      return `${listNames(owned.map((m) => m.name))} ${verb} owned by ${owner.name}, which is also on your list.`;
    }
    return stop(`${names} ${tentative ? `may ${both(members.length)} be` : `are ${both(members.length)}`} owned by ${detail.label}`);
  }
  if (detail.kind === "Address") {
    const where = detail.site?.city
      ? ` in ${titleCase(detail.site.city)}${detail.site.state ? `, ${detail.site.state}` : ""}`
      : "";
    return `${names} ${tentative ? "may be" : "are"} registered at the same physical address${where}.`;
  }
  return stop(`${names} are ${both(members.length)} registered in ${detail.label}`);
}

/** How each member's registry entry compares with the Ultimate Parent reached by walking its direct parents. */
export function declarationNote(detail: ConcentrationDetail): string | null {
  if (detail.kind !== "Ultimate Parent") return null;
  const climbing = detail.members.filter((m: DetailMember) => m.path.length > 1);
  if (!climbing.length) return null;
  const notes = climbing.flatMap((m) => {
    if (m.basis === "declared") return [`${m.name}'s chain of direct parents breaks off, so its declared Ultimate Parent stands in.`];
    if (m.declared_ultimate_parent_lei === null) {
      return [`${m.name}'s registry entry declares no Ultimate Parent; its chain of direct parents leads here.`];
    }
    if (m.declared_ultimate_parent_lei !== detail.key) {
      return [
        `${m.name}'s registry entry declares a different Ultimate Parent (LEI ${m.declared_ultimate_parent_lei}); ` +
          "its chain of direct parents leads here.",
      ];
    }
    return [];
  });
  if (notes.length) return notes.join(" ");
  return climbing.length === 1
    ? "Its registry entry declares that parent too."
    : climbing.length === 2
      ? "Both registry entries declare that parent too."
      : "Every registry entry here declares that parent too.";
}

/** An MCS-150 must be refreshed every two years; a last filing older than that is a sign of Staleness. */
export function staleFiling(lastFiled: string | null, censusAsOf: string | null | undefined): boolean {
  if (!lastFiled || !censusAsOf) return false;
  const limit = new Date(censusAsOf);
  limit.setFullYear(limit.getFullYear() - 2);
  return new Date(lastFiled) < limit;
}
