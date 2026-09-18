import { useState } from "react";
import { api, type Concentration, type Exposure, type Portfolio, type Sample } from "../api";
import {
  causeName,
  listNames,
  memberCount,
  rankedConcentrations,
  sentence,
  tieNote,
  undecidedNames,
} from "../exposure";
import { baselineSummary } from "../exposure";
import { Failure, Header } from "../Header";
import { useLoaded } from "../load";
import { groupMembers } from "../portfolio";
import { href } from "../route";

function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

function shortList(names: string[], limit = 3): string[] {
  return names.length <= limit ? names : [...names.slice(0, limit - 1), `and ${names.length - limit + 1} more`];
}

function Chevron() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#1D5C86" strokeWidth="2" aria-hidden="true">
      <path d="M7 4l6 6-6 6" />
    </svg>
  );
}

function ConcentrationCard({ concentration: c, rank, total, portfolioId }: { concentration: Concentration; rank: number; total: number; portfolioId: string }) {
  const undecided = c.members.filter((m) => !m.firm).map((m) => m.name);
  const names = c.members.map((m) => (m.firm ? m.name : `${m.name} (undecided)`));
  return (
    <a className={`concentration-card${c.tentative ? " tentative" : ""}`} href={href.concentration(portfolioId, c.id)}>
      <span className="mono muted" style={{ fontSize: 18 }}>{rank}</span>
      <span className="stack" style={{ gap: 5 }}>
        <span className="row muted" style={{ gap: 8, fontSize: 13 }}>
          {causeName(c.kind)}
          {c.tentative && <span className="tag tentative" style={{ padding: "2px 8px" }}>Tentative</span>}
        </span>
        <span style={{ fontSize: 19, fontWeight: 700 }}>{c.label}</span>
        {c.tentative && (
          <span style={{ fontSize: 13, color: "var(--amber-ink)" }}>Holds only if {listNames(undecided)} is confirmed</span>
        )}
      </span>
      <span className="stack" style={{ gap: 6, fontSize: 14 }}>
        {shortList(names).map((n) => (
          <span key={n} style={n.endsWith("(undecided)") ? { fontStyle: "italic" } : undefined}>{n}</span>
        ))}
      </span>
      {c.tentative ? (
        <span className="stack" style={{ gap: 2 }}>
          <span style={{ fontWeight: 700, fontSize: 17 }}>{memberCount(c.share_if_possible_matches_hold, total)} of {total}</span>
          <span className="muted" style={{ fontSize: 13 }}>if it holds</span>
        </span>
      ) : (
        <span className="stack" style={{ gap: 2 }}>
          <span style={{ fontWeight: 700, fontSize: 17 }}>{memberCount(c.share, total)} of {total}</span>
          <span className="muted" style={{ fontSize: 13 }}>{percent(c.share)} of Portfolio</span>
        </span>
      )}
      <Chevron />
    </a>
  );
}

function ownershipReason(basis: string): string {
  if (basis === "no GLEIF record") return "no GLEIF record";
  if (basis === "no ownership filing") return "GLEIF record names no parent and gives no reason";
  if (basis.startsWith("exception: ")) return `parent withheld: ${basis.slice("exception: ".length).toLowerCase().replaceAll("_", " ")}`;
  return basis;
}

function ExposureView({ exposure, portfolio, baseline }: { exposure: Exposure; portfolio: Portfolio; baseline: Sample["baseline"] | null }) {
  const [copied, setCopied] = useState(false);
  const { ranked, jurisdictions } = rankedConcentrations(exposure);
  const firm = ranked.filter((c) => !c.tentative);
  const tentative = ranked.filter((c) => c.tentative);
  // Every unconfirmed member the "if confirmed" count includes, in firm concentrations as well as tentative ones.
  const pending = undecidedNames(ranked);
  const undecidedCount = groupMembers(portfolio.members).decide.length;
  const unverifiable = exposure.ownership.members.filter((m) => m.status === "Undisclosed Parent");
  const { matched } = exposure.ownership;
  const total = exposure.members;
  // Tentative concentrations are ranked by their firm share, below the firm ones; ties are among the firm.
  const note = tieNote(firm, total);
  const text = sentence(exposure);
  const id = exposure.portfolio_id;

  return (
    <main className="page">
      <div className="spread" style={{ alignItems: "center" }}>
        <div className="eyebrow">Step 2 of 3 · Exposure</div>
        <a href={href.portfolio(id)} style={{ fontSize: 14 }}>
          Back to the Portfolio{undecidedCount ? ` (${undecidedCount} undecided)` : ""}
        </a>
      </div>

      <section className="panel headline" aria-labelledby="sentence-title">
        <h1 id="sentence-title" className="muted" style={{ fontSize: 13, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase" }}>
          In one sentence
        </h1>
        <p className="headline-sentence">{text}</p>
        <div className="row" style={{ gap: 16 }}>
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={async () => {
              await navigator.clipboard.writeText(text);
              setCopied(true);
            }}
          >
            {copied ? "Copied" : "Copy sentence"}
          </button>
          <span className="muted" style={{ fontSize: 14 }} aria-live="polite">
            {baseline && `For comparison, ${baselineSummary(baseline)}.`}
          </span>
        </div>
      </section>

      <section className="figures" aria-label="Key figures">
        <div className="card figure">
          <div className="figure-number">
            {firm.length} {tentative.length > 0 && <small className="amber">+ {tentative.length} tentative</small>}
          </div>
          <div style={{ fontSize: 15, color: "var(--text-2)" }}>Hidden Concentrations</div>
        </div>
        <div className="card figure">
          <div className="figure-number">
            {exposure.affected} <small>of {total}</small>
          </div>
          <div style={{ fontSize: 15, color: "var(--text-2)" }}>
            suppliers are in one.
            {exposure.affected_if_possible_matches_hold > exposure.affected &&
              ` ${exposure.affected_if_possible_matches_hold} if ${listNames(pending)} ${pending.length === 1 ? "is" : "are"} confirmed.`}
          </div>
        </div>
        <div className="card figure">
          <div className="figure-number">
            {exposure.ownership.unverifiable} <small>of {matched}</small>
          </div>
          <div style={{ fontSize: 15, color: "var(--text-2)" }}>
            Ownership unverifiable: no registry names an owner.
            {exposure.ownership.unmatched > 0 && ` ${exposure.ownership.unmatched} not yet matched are not counted.`}
          </div>
        </div>
      </section>

      <section className="stack-16" aria-labelledby="ranked-title">
        <div className="spread">
          <h2 id="ranked-title" style={{ fontSize: 22 }}>Hidden Concentrations, largest first</h2>
          {note && <span className="muted" style={{ fontSize: 14 }}>{note}</span>}
        </div>
        {ranked.length === 0 ? (
          <div className="card" style={{ padding: "24px 28px", fontSize: 15, color: "var(--text-2)" }}>
            No two suppliers on this list share an owner or a physical address in the registries.
          </div>
        ) : (
          <ol className="plain-list stack-16">
            {ranked.map((c, i) => (
              <li key={c.id}>
                <ConcentrationCard concentration={c} rank={i + 1} total={total} portfolioId={id} />
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="two-col">
        <div className="card figure" style={{ gap: 12 }}>
          <h2 style={{ fontSize: 17 }}>Ownership unverifiable: {exposure.ownership.unverifiable} of {matched}</h2>
          <p style={{ fontSize: 14, lineHeight: 1.5, color: "var(--text-2)" }}>
            No registry names who owns these. They may share a parent with another supplier and we could not tell.
          </p>
          {unverifiable.length ? (
            <ul className="plain-list stack" style={{ gap: 6, fontSize: 14 }}>
              {unverifiable.map((m) => (
                <li key={m.member_id}>
                  {m.name} <span className="muted" style={{ fontSize: 13 }}>({ownershipReason(m.basis)})</span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ fontSize: 14 }}>Every matched supplier names its owner or declares it has none.</p>
          )}
        </div>
        <div className="card figure" style={{ gap: 12 }}>
          <h2 style={{ fontSize: 17 }}>Shared jurisdiction</h2>
          <p style={{ fontSize: 14, lineHeight: 1.5, color: "var(--text-2)" }}>
            Registered under the same state law. A weaker Common Cause than an owner or a site, so it is not ranked.
          </p>
          {jurisdictions.length ? (
            <ul className="plain-list stack" style={{ gap: 8 }}>
              {jurisdictions.map((j) => (
                <li key={j.id} style={{ display: "grid", gridTemplateColumns: "72px 70px minmax(0, 1fr)", gap: 12, fontSize: 14, alignItems: "baseline" }}>
                  <span className="mono" style={{ fontWeight: 500 }}>{j.label}</span>
                  <span style={{ fontWeight: 600 }}>{memberCount(j.share, total)} of {total}</span>
                  <span style={{ color: "var(--text-2)" }}>
                    {listNames(j.members.map((m) => (m.firm ? m.name : `${m.name} (undecided)`)))}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ fontSize: 14 }}>No two matched suppliers are registered in the same jurisdiction.</p>
          )}
        </div>
      </section>
      {exposure.ownership.disagreements.length > 0 && (
        <section className="card figure" style={{ gap: 12 }}>
          <h2 style={{ fontSize: 17 }}>Where the registry contradicts itself</h2>
          <p style={{ fontSize: 14, lineHeight: 1.5, color: "var(--text-2)" }}>
            Following each company's direct parent upward reaches a different top company than the one its own entry
            declares. We follow the chain; the disagreement is worth a look.
          </p>
          <ul className="plain-list stack" style={{ gap: 6, fontSize: 14 }}>
            {exposure.ownership.disagreements.map((d) => (
              <li key={`${d.member_id}:${d.lei}`}>
                {d.name}: <span className="mono" style={{ fontSize: 13 }}>walked to LEI {d.walked_lei}, declares LEI {d.declared_lei}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

export function ExposureScreen({ portfolioId }: { portfolioId: string }) {
  const loaded = useLoaded(portfolioId, async () => {
    const [exposure, portfolio] = await Promise.all([api.exposure(portfolioId), api.portfolio(portfolioId)]);
    const baseline = portfolio.sample ? (await api.sample()).baseline : null;
    return { exposure, portfolio, baseline };
  });
  return (
    <>
      <Header current={2} portfolioId={portfolioId} />
      {loaded.state === "loading" && <main className="page loading">Looking for shared owners and sites…</main>}
      {loaded.state === "failed" && <main className="page"><Failure error={loaded.error} /></main>}
      {loaded.state === "ready" && <ExposureView {...loaded.value} />}
    </>
  );
}
