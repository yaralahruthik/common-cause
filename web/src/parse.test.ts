import { describe, expect, it } from "vitest";
import { formatMember, parseCsv, parseNames } from "./parse";

describe("parseNames", () => {
  it("reads one name per line and skips blank lines", () => {
    expect(parseNames("Koch Foods LLC\n\n  Bar-S Foods Co  \n")).toEqual([
      { name: "Koch Foods LLC", state: null, city: null },
      { name: "Bar-S Foods Co", state: null, city: null },
    ]);
  });

  it("reads a state after the last comma", () => {
    expect(parseNames("Prairie Farms Dairy, il")).toEqual([{ name: "Prairie Farms Dairy", state: "IL", city: null }]);
  });

  it("reads a city and state after the last comma", () => {
    expect(parseNames("Herr Foods Inc, Nottingham PA")).toEqual([
      { name: "Herr Foods Inc", state: "PA", city: "Nottingham" },
    ]);
  });

  it("reads a city alone after the last comma", () => {
    expect(parseNames("Herr Foods Inc, Nottingham")).toEqual([
      { name: "Herr Foods Inc", state: null, city: "Nottingham" },
    ]);
  });

  it("keeps a legal form after a comma as part of the name", () => {
    expect(parseNames("Acme Foods, Inc.\nNestle Holdings, Inc., DE")).toEqual([
      { name: "Acme Foods, Inc.", state: null, city: null },
      { name: "Nestle Holdings, Inc.", state: "DE", city: null },
    ]);
  });
});

describe("parseCsv", () => {
  it("reads name, state and city columns by their headers, in any order and case", () => {
    const csv = 'State,Supplier Name,City\nTX,"Rolling Frito-Lay Sales, LP",\n,Naked Juice LLC,Chicago\n';
    expect(parseCsv(csv)).toEqual([
      { name: "Rolling Frito-Lay Sales, LP", state: "TX", city: null },
      { name: "Naked Juice LLC", state: null, city: "Chicago" },
    ]);
  });

  it("takes the first column as the name when no header says name", () => {
    expect(parseCsv('Koch Foods LLC\n"Herr Foods ""Snacks"" Inc"\n')).toEqual([
      { name: "Koch Foods LLC", state: null, city: null },
      { name: 'Herr Foods "Snacks" Inc', state: null, city: null },
    ]);
  });
});

describe("formatMember", () => {
  it("writes a member back as a line that reads the same", () => {
    const members = [
      { name: "Herr Foods Inc", state: "PA", city: "Nottingham" },
      { name: "Acme Foods, Inc.", state: null, city: null },
      { name: "Koch Foods LLC", state: "TN", city: null },
    ];
    expect(parseNames(members.map(formatMember).join("\n"))).toEqual(members);
  });
});
