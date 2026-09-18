import { describe, expect, it } from "vitest";
import { match, member } from "./fixtures";
import { groupMembers, recordLabel } from "./portfolio";

describe("groupMembers", () => {
  it("puts a Firm or confirmed Match under Matched, ahead of any Possible ones beside it", () => {
    const firm = member(1, "Hiland", [match("fmcsa:1", "Firm"), match("fmcsa:2", "Possible")]);
    const confirmed = member(2, "Naked", [match("fmcsa:3", "Possible"), match("gleif:A", "Possible", "confirmed")]);

    const groups = groupMembers([firm, confirmed]);

    expect(groups.matched.map((m) => [m.member.member_id, m.match.entity_id])).toEqual([
      [1, "fmcsa:1"],
      [2, "gleif:A"],
    ]);
    expect(groups.decide).toEqual([]);
  });

  it("asks for a decision on the Possible Matches not yet judged", () => {
    const naked = member(2, "Naked", [match("fmcsa:3", "Possible", "rejected"), match("gleif:A", "Possible")]);

    expect(groupMembers([naked]).decide.map((d) => d.candidates.map((c) => c.entity_id))).toEqual([["gleif:A"]]);
  });

  it("lists a name with nothing left to match as not found, with what the analyst rejected", () => {
    const nothing = member(3, "Zenith", []);
    const rejected = member(4, "Koch", [match("fmcsa:640137", "Firm", "rejected")]);

    const groups = groupMembers([nothing, rejected]);

    expect(groups.notFound.map((n) => [n.member.member_id, n.rejected.map((r) => r.entity_id)])).toEqual([
      [3, []],
      [4, ["fmcsa:640137"]],
    ]);
  });
});

describe("recordLabel", () => {
  it("names a record by the registry's own id", () => {
    expect(recordLabel("fmcsa:926150")).toBe("USDOT 926150");
    expect(recordLabel("gleif:549300ZUAM7OFVH6ZB49")).toBe("LEI 549300ZUAM7OFVH6ZB49");
  });
});
