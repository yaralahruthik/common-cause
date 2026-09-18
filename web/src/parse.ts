import type { MemberIn } from "./api";

// US states, DC and territories: the codes the registries use for a state.
const STATES = new Set(
  (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR " +
    "PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR GU VI AS MP"
  ).split(" "),
);

// Legal forms that follow a comma inside a company's own name ("Acme Foods, Inc.").
const LEGAL_FORMS = new Set(
  "INC INCORPORATED LLC CO COMPANY CORP CORPORATION LP LLP LTD LIMITED PLC SA NA PC PLLC".split(" "),
);

function stateCode(text: string): string | null {
  const code = text.trim().toUpperCase();
  return STATES.has(code) ? code : null;
}

/** One line: a name, then optionally a comma and a state, a city, or a city and state. */
function parseLine(line: string): MemberIn {
  const comma = line.lastIndexOf(",");
  if (comma < 0) return { name: line, state: null, city: null };
  const name = line.slice(0, comma).trim();
  const tail = line.slice(comma + 1).trim();
  if (!name || !tail || LEGAL_FORMS.has(tail.toUpperCase().replace(/[.\s]/g, ""))) {
    return { name: line, state: null, city: null };
  }
  const state = stateCode(tail);
  if (state) return { name, state, city: null };
  const cityState = /^(.+?)\s+(\S{2})$/.exec(tail);
  const trailingState = cityState ? stateCode(cityState[2]!) : null;
  if (cityState && trailingState) return { name, state: trailingState, city: cityState[1]! };
  return { name, state: null, city: tail };
}

/** A pasted list: one name per line, blank lines skipped. */
export function parseNames(text: string): MemberIn[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map(parseLine);
}

/** The line `parseNames` reads back as the same member. */
export function formatMember(member: MemberIn): string {
  const place = [member.city, member.state].filter(Boolean).join(" ");
  return place ? `${member.name}, ${place}` : member.name;
}

/** Rows of a CSV file, quoted fields and doubled quotes included. */
function csvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i]!;
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else field += c;
  }
  if (field || row.length) rows.push([...row, field]);
  return rows.filter((r) => r.some((f) => f.trim()));
}

/** A CSV of names. A header naming a `name` column (and `state`, `city`) is used; otherwise column 1 is the name. */
export function parseCsv(text: string): MemberIn[] {
  const rows = csvRows(text.replace(/^﻿/, ""));
  const header = (rows[0] ?? []).map((h) => h.trim().toLowerCase());
  const nameColumn = header.findIndex((h) => h.includes("name"));
  const hasHeader = nameColumn >= 0;
  const column = (word: string) => (hasHeader ? header.findIndex((h) => h.includes(word)) : -1);
  const [n, s, c] = [hasHeader ? nameColumn : 0, column("state"), column("city")];
  const value = (row: string[], i: number) => (i >= 0 ? row[i]?.trim() || null : null);
  return rows
    .slice(hasHeader ? 1 : 0)
    .map((row) => ({ name: value(row, n) ?? "", state: value(row, s)?.toUpperCase() ?? null, city: value(row, c) }))
    .filter((m) => m.name);
}
