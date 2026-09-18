import { describe, expect, it } from "vitest";
import { detailMember } from "./fixtures";
import { layoutTree } from "./tree";

describe("layoutTree", () => {
  it("places the Ultimate Parent on top, shared hops once, and each member under its own chain", () => {
    const tree = layoutTree([detailMember(1, true, ["PURINA", "HOLDINGS", "NESTLE"]), detailMember(2, true, ["USA", "HOLDINGS", "NESTLE"])]);

    expect(tree.nodes.map((n) => [n.lei, n.role, n.depth, n.x])).toEqual([
      ["NESTLE", "root", 0, 0.5],
      ["HOLDINGS", "intermediate", 1, 0.5],
      ["PURINA", "member", 2, 0],
      ["USA", "member", 2, 1],
    ]);
    expect(tree.edges.map((e) => [e.from, e.to, e.dashed])).toEqual([
      ["PURINA", "HOLDINGS", false],
      ["HOLDINGS", "NESTLE", false],
      ["USA", "HOLDINGS", false],
    ]);
    expect(tree.levels).toBe(3);
    expect(tree.slots).toBe(2);
  });

  it("marks a member that is itself the Ultimate Parent", () => {
    const tree = layoutTree([detailMember(1, true, ["STRATTON"]), detailMember(2, true, ["STAR", "STRATTON"])]);

    const root = tree.nodes[0]!;
    expect([root.lei, root.role, root.members.map((m) => m.member_id)]).toEqual(["STRATTON", "root", [1]]);
  });

  it("dashes what rests only on an unconfirmed member, and marks a declared last hop", () => {
    const tree = layoutTree([
      detailMember(1, true, ["FRITO", "PEPSICO"]),
      detailMember(2, false, ["NAKED", "PEPSICO"]),
      detailMember(3, true, ["BROKEN", "PEPSICO"], "declared"),
    ]);

    expect(tree.edges.map((e) => [e.from, e.dashed, e.declared])).toEqual([
      ["FRITO", false, false],
      ["NAKED", true, false],
      ["BROKEN", false, true],
    ]);
    expect(tree.nodes.find((n) => n.lei === "NAKED")?.dashed).toBe(true);
  });
});

describe("layoutTree on a looping path", () => {
  it("places each company once instead of recursing forever", () => {
    const tree = layoutTree([detailMember(1, true, ["B", "C", "B"])]);
    expect(tree.nodes.map((n) => n.lei).sort()).toEqual(["B", "C"]);
  });
});
