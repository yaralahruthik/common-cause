import { describe, expect, it } from "vitest";
import type { ConcentrationDetail, DetailMember } from "./api";
import { declarationNote, detailHeading, staleFiling } from "./detail";
import { detailMember } from "./fixtures";

function named(member: DetailMember, name: string, declared: string | null = "TOP"): DetailMember {
  return { ...member, name, declared_ultimate_parent_lei: declared };
}

function detail(overrides: Partial<ConcentrationDetail>): ConcentrationDetail {
  return {
    id: "c",
    kind: "Ultimate Parent",
    key: "TOP",
    label: "NESTLÉ S.A.",
    total: 15,
    share: 2 / 15,
    share_if_possible_matches_hold: 2 / 15,
    tentative: false,
    rank: 1,
    ranked: 1,
    members: [],
    site: null,
    as_of: {},
    ...overrides,
  };
}

describe("detailHeading", () => {
  it("names the members and the parent they share", () => {
    const members = [named(detailMember(1, true, ["A", "TOP"]), "Nestle Purina"), named(detailMember(2, true, ["B", "TOP"]), "Nestle USA")];
    expect(detailHeading(detail({ members }))).toBe("Nestle Purina and Nestle USA are both owned by NESTLÉ S.A.");
    expect(detailHeading(detail({ members, tentative: true }))).toBe(
      "Nestle Purina and Nestle USA may both be owned by NESTLÉ S.A.",
    );
  });

  it("says so when one member owns the others", () => {
    const members = [named(detailMember(1, true, ["TOP"]), "Mrs Stratton's Salads", null), named(detailMember(2, true, ["STAR", "TOP"]), "Star Food Products")];
    expect(detailHeading(detail({ members }))).toBe(
      "Star Food Products is owned by Mrs Stratton's Salads, which is also on your list.",
    );
  });

  it("places members at a shared address in its city", () => {
    const members = [named(detailMember(1, true, []), "Prairie Farms Dairy"), named(detailMember(2, true, []), "East Side Jersey Dairy")];
    const site = { street: "3744 STAUNTON ROAD", city: "EDWARDSVILLE", state: "IL", zip: "62025", names_registered: 4, agent_threshold: 10, others: [] };
    expect(detailHeading(detail({ kind: "Address", members, site }))).toBe(
      "Prairie Farms Dairy and East Side Jersey Dairy are registered at the same physical address in Edwardsville, IL.",
    );
  });
});

describe("declarationNote", () => {
  it("says when every registry entry declares the same parent", () => {
    const members = [named(detailMember(1, true, ["A", "TOP"]), "A"), named(detailMember(2, true, ["B", "TOP"]), "B")];
    expect(declarationNote(detail({ members }))).toBe("Both registry entries declare that parent too.");
  });

  it("names a member whose entry declares another parent, or whose chain breaks off", () => {
    const members = [
      named(detailMember(1, true, ["A", "TOP"]), "Acme", "ELSEWHERE"),
      named(detailMember(2, true, ["B", "TOP"], "declared"), "Brandco"),
      named(detailMember(3, true, ["C", "TOP"]), "Crate", null),
    ];
    expect(declarationNote(detail({ members }))).toBe(
      "Acme's registry entry declares a different Ultimate Parent (LEI ELSEWHERE); its chain of direct parents leads here. " +
        "Brandco's chain of direct parents breaks off, so its declared Ultimate Parent stands in. " +
        "Crate's registry entry declares no Ultimate Parent; its chain of direct parents leads here.",
    );
  });
});

describe("staleFiling", () => {
  it("flags a last filing more than two years before the census", () => {
    expect(staleFiling("2024-02-20", "2026-09-14")).toBe(true);
    expect(staleFiling("2025-09-16", "2026-09-14")).toBe(false);
    expect(staleFiling(null, "2026-09-14")).toBe(false);
  });
});
