import { describe, expect, it } from "vitest";
import type { Concentration } from "./api";
import { concentrationMember, exposure } from "./fixtures";
import { baselineSummary, memberCount, rankedConcentrations, sentence, tieNote, undecidedNames } from "./exposure";

function concentration(kind: Concentration["kind"], share: number, tentative = false): Concentration {
  return {
    id: `${kind}${share}`,
    kind,
    key: kind,
    label: kind,
    share,
    share_if_possible_matches_hold: share,
    tentative,
    members: [],
  };
}

describe("sentence", () => {
  it("says how many suppliers share an owner or a site, and how many owners cannot be seen", () => {
    expect(sentence(exposure({ affected: 7 }))).toBe(
      "7 of your 15 suppliers share an owner or a site with another supplier on this list, " +
        "and we cannot see who owns 5 of the 13 we matched.",
    );
  });

  it("says so plainly when none do and every owner is visible", () => {
    const clear = exposure({
      affected: 0,
      ownership: { total: 3, matched: 3, unmatched: 0, unverifiable: 0, members: [], disagreements: [] },
      members: 3,
    });
    expect(sentence(clear)).toBe(
      "None of your 3 suppliers shares an owner or a site with another supplier on this list, " +
        "and every one of the 3 we matched names its owner or declares it has none.",
    );
  });
});

describe("rankedConcentrations", () => {
  it("keeps the ranked order and sets shared jurisdictions apart", () => {
    const ranked = [concentration("Ultimate Parent", 0.2), concentration("Address", 0.1)];
    const jurisdiction = concentration("Jurisdiction", 0.4);

    expect(rankedConcentrations(exposure({ concentrations: [...ranked, jurisdiction] }))).toEqual({
      ranked,
      jurisdictions: [jurisdiction],
    });
  });
});

describe("tieNote", () => {
  it("explains the order when every concentration is the same size", () => {
    const all = [concentration("Ultimate Parent", 2 / 15), concentration("Address", 2 / 15)];
    expect(tieNote(all, 15)).toBe("Each is 2 of 15, so ties are ordered by kind of Common Cause");
  });

  it("explains ties only where there are some", () => {
    const some = [concentration("Ultimate Parent", 3 / 15), concentration("Address", 2 / 15)];
    expect(tieNote(some, 15)).toBeNull();
    const tied = [...some, concentration("Address", 2 / 15)];
    expect(tieNote(tied, 15)).toBe("Equal sizes are ordered by kind of Common Cause");
  });
});

describe("undecidedNames", () => {
  it("names the members that tentative concentrations rest on, once each", () => {
    const tentative = {
      ...concentration("Ultimate Parent", 1 / 15, true),
      members: [concentrationMember(1, "Rolling Frito-Lay"), concentrationMember(2, "Naked Juice LLC", false)],
    };
    expect(undecidedNames([tentative, tentative])).toEqual(["Naked Juice LLC"]);
  });
});

describe("memberCount", () => {
  it("turns a share of the Portfolio back into a count", () => {
    expect(memberCount(2 / 15, 15)).toBe(2);
  });
});

describe("baselineSummary", () => {
  const baseline = { description: "", members: Array(15).fill({ name: "x", state: null, city: null }), matched: 14, unverifiable: 14 };

  it("says plainly when the random list finds nothing", () => {
    expect(baselineSummary({ ...baseline, concentrations: 0, affected: 0 })).toBe(
      "a random list of 15 fleets from the same data finds no Hidden Concentrations",
    );
  });

  it("gives the count and the members in one when it finds some", () => {
    expect(baselineSummary({ ...baseline, concentrations: 1, affected: 2 })).toBe(
      "a random list of 15 fleets from the same data finds 1 Hidden Concentration, with 2 of its members firmly in one",
    );
  });
});
