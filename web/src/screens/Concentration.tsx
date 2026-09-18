import { useState } from "react";
import { api, type ConcentrationDetail, type DetailMember, NotFound, type OwnershipStatus, type Registration } from "../api";
import { declarationNote, detailHeading, staleFiling } from "../detail";
import { causeName, memberCount } from "../exposure";
import { Failure, Header } from "../Header";
import { useLoaded } from "../load";
import { dotUrl, leiUrl, place, recordLabel, recordSource } from "../portfolio";
import { href } from "../route";
import { layoutTree, type TreeNode } from "../tree";

const SLOT = 370;
const NODE_W = 330;
const NODE_H = 96;
const LEVEL = 150;

function Arrowhead({ id }: { id: string }) {
  return (
    <defs>
      <marker id={id} viewBox="0 0 10 10" refX="5" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M0 0L10 5L0 10z" fill="#5A5F66" />
      </marker>
    </defs>
  );
}

function registrationCount(member: DetailMember): string {
  const n = member.registrations.length;
  return n === 0 ? "no Registration" : n === 1 ? "1 Registration" : `${n} Registrations`;
}

function nodeKicker(node: TreeNode): string {
  const where = node.jurisdiction ? ` · ${node.jurisdiction}` : "";
  const member = node.members[0];
  const trucks = member ? ` · ${registrationCount(member)}` : "";
  if (node.role === "root") return `Ultimate Parent${where}${member ? ` · your supplier${trucks}` : ""}`;
  if (node.role === "intermediate") return `Intermediate${where}`;
  return `Your supplier${where}${node.dashed ? " · unconfirmed" : trucks}`;
}

function OwnershipTree({ detail }: { detail: ConcentrationDetail }) {
  const tree = layoutTree(detail.members);
  const width = Math.max(tree.slots, 1) * SLOT;
  const height = (tree.levels - 1) * LEVEL + NODE_H + 4;
  const byLei = new Map(tree.nodes.map((n) => [n.lei, n]));
  const center = (n: TreeNode) => n.x * SLOT + SLOT / 2;
  const hasDashed = tree.edges.some((e) => e.dashed);
  const hasDeclared = tree.edges.some((e) => e.declared);
  return (
    <section className="panel" aria-labelledby="path-title">
      <div className="spread">
        <h2 id="path-title" style={{ fontSize: 18 }}>Ownership path</h2>
        <span className="muted" style={{ fontSize: 13 }}>
          Arrows point to the company that consolidates it in its accounts
          {hasDashed && ". Dashed: rests on a match you have not confirmed"}
          {hasDeclared && ". Dotted: the chain breaks off; the declared Ultimate Parent stands in"}
        </span>
      </div>
      <div className="diagram-scroll">
        <div className="diagram" style={{ width, height }}>
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} fill="none" aria-hidden="true">
            <Arrowhead id="tree-arrow" />
            {tree.edges.map((edge) => {
              const child = byLei.get(edge.from)!;
              const parent = byLei.get(edge.to)!;
              const top = child.depth * LEVEL;
              const mid = top - (LEVEL - NODE_H) / 2;
              return (
                <path
                  key={`${edge.from}>${edge.to}`}
                  d={`M${center(child)} ${top} V${mid} H${center(parent)} V${parent.depth * LEVEL + NODE_H + 4}`}
                  stroke={edge.dashed ? "#B26B00" : "#5A5F66"}
                  strokeWidth="1.5"
                  strokeDasharray={edge.declared ? "2 4" : edge.dashed ? "6 5" : undefined}
                  markerEnd="url(#tree-arrow)"
                />
              );
            })}
          </svg>
          {tree.nodes.map((node) => {
            const kind = node.role === "root" ? "node-root" : node.dashed ? "node-dashed" : node.role === "member" ? "node-member" : "node-intermediate";
            return (
              <div
                key={node.lei}
                className={`node ${kind}`}
                style={{ left: center(node) - NODE_W / 2, top: node.depth * LEVEL, width: NODE_W, height: NODE_H }}
              >
                <span className="node-kicker">{nodeKicker(node)}</span>
                <a className="node-name" href={leiUrl(node.lei)} target="_blank" rel="noreferrer" title={node.name ?? undefined}>
                  {node.name ?? `LEI ${node.lei}`}
                </a>
                <span className="node-ids">
                  LEI {node.lei}
                  {node.name === null && " · not in the GLEIF extract"}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      {declarationNote(detail) && (
        <p style={{ fontSize: 14, color: "var(--text-2)", borderTop: "1px solid var(--line-soft)", paddingTop: 14 }}>
          {declarationNote(detail)}
        </p>
      )}
    </section>
  );
}

function ownershipLine(status: OwnershipStatus | null, basis: string): { text: string; hidden: boolean } {
  if (status === "Undisclosed Parent") {
    return { text: basis === "no GLEIF record" ? "Undisclosed Parent: no GLEIF record" : "Undisclosed Parent: owner withheld", hidden: true };
  }
  if (status === "Declared Independent") {
    const reason = basis.startsWith("exception: ") && basis.includes("NATURAL_PERSONS") ? ": owned by natural persons" : "";
    return { text: `Declared Independent${reason}`, hidden: false };
  }
  return { text: status ?? "Ownership not known yet", hidden: false };
}

function SiteDiagram({ detail }: { detail: ConcentrationDetail }) {
  const site = detail.site!;
  const members = detail.members;
  const width = Math.max(members.length * SLOT, SLOT * 2);
  const offset = (width - members.length * SLOT) / 2;
  const siteCenter = width / 2;
  const others = site.others.slice(0, 5);
  const more = site.others.length - others.length;
  return (
    <section className="panel" aria-labelledby="site-title">
      <div className="spread">
        <h2 id="site-title" style={{ fontSize: 18 }}>Shared site</h2>
        <span className="muted" style={{ fontSize: 13 }}>Physical address on each record</span>
      </div>
      <div className="diagram-scroll">
        <div className="diagram" style={{ width, height: LEVEL + NODE_H }}>
          <svg width={width} height={LEVEL + NODE_H} fill="none" aria-hidden="true">
            <Arrowhead id="site-arrow" />
            {members.map((m, i) => (
              <path
                key={m.member_id}
                d={`M${offset + i * SLOT + SLOT / 2} ${NODE_H} V${NODE_H + (LEVEL - NODE_H) / 2} H${siteCenter} V${LEVEL - 4}`}
                stroke={m.firm ? "#5A5F66" : "#B26B00"}
                strokeWidth="1.5"
                strokeDasharray={m.firm ? undefined : "6 5"}
                markerEnd="url(#site-arrow)"
              />
            ))}
          </svg>
          {members.map((m, i) => {
            const own = ownershipLine(m.ownership_status, m.ownership_basis);
            const first = m.registrations[0];
            return (
              <div
                key={m.member_id}
                className={`node ${m.firm ? "node-member" : "node-dashed"}`}
                style={{ left: offset + i * SLOT + (SLOT - NODE_W) / 2, top: 0, width: NODE_W, height: NODE_H }}
              >
                <span className="node-kicker">
                  Your supplier{first ? ` · USDOT ${first.dot_number}` : ""}{m.firm ? "" : " · unconfirmed"}
                </span>
                <span className="node-name" style={{ textDecoration: "none" }} title={m.match.name}>{m.match.name}</span>
                <span style={{ fontSize: 13, color: own.hidden ? "var(--amber-ink)" : "var(--text-2)" }}>{own.text}</span>
                {m.leis[0] && (
                  <a className="node-ids" href={leiUrl(m.leis[0])} target="_blank" rel="noreferrer">LEI {m.leis[0]}</a>
                )}
              </div>
            );
          })}
          <div className="node node-root" style={{ left: siteCenter - 175, top: LEVEL, width: 350, height: NODE_H - 4 }}>
            <span className="node-kicker">Shared address</span>
            <span style={{ fontSize: 17, fontWeight: 700 }}>{site.street}</span>
            <span style={{ fontSize: 13, color: "var(--text-2)" }}>{[site.city, site.state, site.zip].filter(Boolean).join(" ")}</span>
          </div>
        </div>
      </div>
      <div style={{ borderTop: "1px solid var(--line-soft)", paddingTop: 16, display: "grid", gridTemplateColumns: "24px minmax(0, 1fr)", gap: 12, fontSize: 14, lineHeight: 1.55, color: "var(--text-2)" }}>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#2F7D4F" strokeWidth="2" aria-hidden="true">
          <path d="M4 10.5l4 4 8-9" />
        </svg>
        <span>
          <strong style={{ color: "var(--text)" }}>Not an Agent Address.</strong> {site.names_registered} distinct names
          are registered here. More than {site.agent_threshold} would mark a registered agent or a mail drop, and the
          address would not count.{" "}
          {others.length === 0
            ? "No one else is registered here."
            : <>
                The other{site.others.length === 1 ? " is" : "s are"}{" "}
                {others.map((o, i) => (
                  <span key={o.name}>
                    {i > 0 && (i === others.length - 1 && more === 0 ? " and " : ", ")}
                    {o.name} (
                    {o.record_ids.map((r, j) => (
                      <span key={r}>
                        {j > 0 && ", "}
                        <a href={r.startsWith("fmcsa:") ? dotUrl(r.slice(6)) : leiUrl(r.slice(6))} target="_blank" rel="noreferrer">
                          {recordLabel(r)}
                        </a>
                      </span>
                    ))}
                    )
                  </span>
                ))}
                {more > 0 && ` and ${more} more`}, {site.others.length === 1 ? "not" : "none of them"} on your list.
              </>}
        </span>
      </div>
    </section>
  );
}

function WarningIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#A12C1C" strokeWidth="1.8" aria-hidden="true">
      <path d="M7 1.5l6 11H1z" />
      <path d="M7 6v3M7 10.8v.2" />
    </svg>
  );
}

function RegistrationRow({ registration: r, censusAsOf }: { registration: Registration; censusAsOf: string | null | undefined }) {
  const stale = r.status !== "Active" || staleFiling(r.last_filed, censusAsOf);
  const statusClass = r.status === "Active" ? "" : r.status === "Inactive" ? " inactive" : " other";
  return (
    <div className={`reg-grid reg-row${r.out_of_service.length ? " out-of-service" : stale ? " stale" : ""}`} role="row">
      <a role="cell" className="mono" href={dotUrl(r.dot_number)} target="_blank" rel="noreferrer">{r.dot_number}</a>
      <span role="cell" className="stack" style={{ gap: 2 }}>
        <span>{r.name}</span>
        {r.dba_name && <span className="muted" style={{ fontSize: 12 }}>doing business as {r.dba_name}</span>}
      </span>
      <span role="cell" className={`status${statusClass}`}>
        <span className="status-dot" aria-hidden="true" />
        {r.status ?? "Not given"}
      </span>
      <span role="cell">{r.power_units?.toLocaleString("en-US") ?? "—"}</span>
      <span role="cell">{[r.street, [r.city, r.state, r.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ")}</span>
      <span role="cell" className="stack" style={{ gap: 2 }}>
        <span>{r.last_filed ?? "Not given"}</span>
        {staleFiling(r.last_filed, censusAsOf) && (
          <span style={{ fontSize: 12, color: "var(--amber-ink)" }}>over 2 years before the census</span>
        )}
      </span>
      <span role="cell">
        {r.out_of_service.length === 0 ? (
          <span style={{ color: "var(--text-2)" }}>None on record</span>
        ) : (
          <span className="oos">
            <span className="oos-count"><WarningIcon />{r.out_of_service.length} {r.out_of_service.length === 1 ? "order" : "orders"}</span>
            {r.out_of_service.map((o, i) => (
              <span key={i} style={{ fontSize: 13 }}>
                <span style={{ color: "var(--text-2)" }}>{o.ordered ?? "Undated"} · {o.reason ?? "no reason given"}</span>
                <br />
                <span className="muted">
                  {o.rescinded ? `Rescinded ${o.rescinded}` : `Not rescinded · order ${(o.status ?? "status not given").toLowerCase()}`}
                </span>
              </span>
            ))}
          </span>
        )}
      </span>
    </div>
  );
}

function Registrations({ detail }: { detail: ConcentrationDetail }) {
  const census = detail.as_of["FMCSA census"];
  return (
    <section className="card registrations" aria-labelledby="reg-title" style={{ borderRadius: 12 }}>
      <div className="spread" style={{ padding: "24px 32px 16px" }}>
        <h2 id="reg-title" style={{ fontSize: 18 }}>Trucks on the road: Registrations</h2>
        <span className="muted" style={{ fontSize: 13 }}>
          FMCSA census as of {census ?? "unknown"} · out-of-service orders as of {detail.as_of["FMCSA out-of-service orders"] ?? "unknown"}
        </span>
      </div>
      <div role="table" aria-labelledby="reg-title">
        <div className="reg-grid reg-head" role="row">
          {["USDOT", "Name on file", "Status", "Power units", "Physical address", "Last filed", "Out of service"].map((h) => (
            <span role="columnheader" key={h}>{h}</span>
          ))}
        </div>
        {detail.members.map((m) => (
          <div role="rowgroup" key={m.member_id}>
            <div className="reg-member" role="row">
              <strong role="rowheader">{m.name}</strong>
              {!m.firm && <span style={{ color: "var(--amber-ink)" }}>(unconfirmed)</span>}
              <span className="muted" style={{ fontSize: 13 }}>
                matched to {m.match.name}: {m.match.verdict === "confirmed" ? "you confirmed it" : m.match.evidence}
              </span>
            </div>
            {m.registrations.length ? (
              m.registrations.map((r) => <RegistrationRow key={r.dot_number} registration={r} censusAsOf={census} />)
            ) : (
              <div role="row" style={{ padding: "8px 32px 20px", fontSize: 14, color: "var(--text-2)" }}>
                <span role="cell">
                  No FMCSA Registration.
                  {m.leis.length ? " This supplier is known from its GLEIF record only." : ""}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function DecideBanner({ member, portfolioId, onDecided }: { member: DetailMember; portfolioId: string; onDecided: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<unknown>(null);
  const m = member.match;
  const loc = place(m.city, m.state);
  const alternatives = member.alternatives;
  const decide = async (verdict: "confirmed" | "rejected") => {
    setBusy(true);
    setProblem(null);
    try {
      await api.recordVerdict(portfolioId, member.member_id, m.entity_id, verdict);
      await onDecided();
    } catch (error) {
      setProblem(error);
    } finally {
      // The banner stays when the concentration survives through another of the member's Matches.
      setBusy(false);
    }
  };
  return (
    <section className="decide-banner" aria-labelledby={`decide-${member.member_id}`}>
      <div className="stack" style={{ gap: 8 }}>
        <h2 id={`decide-${member.member_id}`} style={{ fontSize: 18, color: "var(--amber-deep)" }}>
          This holds only if you confirm one match
        </h2>
        <p style={{ fontSize: 15, lineHeight: 1.55, color: "var(--text-2)" }}>
          Is the {member.name} on your list the {recordSource(m.record_id)} record{" "}
          <span className="mono" style={{ fontSize: 14 }}>{recordLabel(m.record_id)}</span>, {m.name}
          {loc && ` (${loc})`}?{" "}
          {alternatives.length === 1 && (
            <>
              Another record comes close: {recordSource(alternatives[0]!.record_id)}{" "}
              <span className="mono" style={{ fontSize: 14 }}>{recordLabel(alternatives[0]!.record_id)}</span>, {alternatives[0]!.name}
              {place(alternatives[0]!.city, alternatives[0]!.state) && `, ${place(alternatives[0]!.city, alternatives[0]!.state)}`}.{" "}
            </>
          )}
          {alternatives.length > 1 && `${alternatives.length} other records come close. `}
          If it is not this one, this concentration goes away.
        </p>
        {problem !== null && <Failure error={problem} />}
      </div>
      <div className="row" style={{ gap: 10 }}>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => decide("confirmed")}>
          Yes, this is it
        </button>
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => decide("rejected")}>
          Not this
        </button>
      </div>
    </section>
  );
}

function DetailView({ detail, portfolioId, reload }: { detail: ConcentrationDetail; portfolioId: string; reload: () => Promise<void> }) {
  const count = memberCount(detail.tentative ? detail.share_if_possible_matches_hold : detail.share, detail.total);
  const isJurisdiction = detail.kind === "Jurisdiction";
  return (
    <main className="page page-tight">
      <nav aria-label="Breadcrumb" className="row muted" style={{ gap: 8, fontSize: 14 }}>
        <a href={href.exposure(portfolioId)}>Exposure</a>
        <span aria-hidden="true">/</span>
        <span aria-current="page">
          {isJurisdiction ? "Shared jurisdiction" : "Concentration"} {detail.rank} of {detail.ranked}
        </span>
      </nav>
      <div className="stack" style={{ gap: 14 }}>
        <div className="row" style={{ gap: 8, fontSize: 13 }}>
          <span className={`tag ${detail.tentative ? "tentative" : "firm"}`}>{detail.tentative ? "Tentative" : "Firm"}</span>
          <span className="tag">{causeName(detail.kind)}</span>
          <span className="tag">{count} of {detail.total} suppliers{detail.tentative ? " if it holds" : ""}</span>
        </div>
        <h1 className="title-detail">{detailHeading(detail)}</h1>
        {detail.kind === "Address" && (
          <p style={{ fontSize: 16, color: "var(--text-2)" }}>
            A site they share would stop them together, whoever owns them.
          </p>
        )}
      </div>
      {detail.members.filter((m) => !m.firm).map((m) => (
        <DecideBanner key={m.member_id} member={m} portfolioId={portfolioId} onDecided={reload} />
      ))}
      {detail.kind === "Ultimate Parent" && <OwnershipTree detail={detail} />}
      {detail.kind === "Address" && detail.site && <SiteDiagram detail={detail} />}
      <Registrations detail={detail} />
      <section className="sources" aria-labelledby="sources-title">
        <h2 id="sources-title" style={{ fontSize: 16, color: "var(--text)" }}>Sources</h2>
        <ul>
          <li>GLEIF Level 1 and Level 2, as of {detail.as_of["GLEIF"] ?? "unknown"}</li>
          <li>FMCSA carrier census, as of {detail.as_of["FMCSA census"] ?? "unknown"}</li>
          <li>FMCSA out-of-service orders, as of {detail.as_of["FMCSA out-of-service orders"] ?? "unknown"}</li>
        </ul>
      </section>
    </main>
  );
}

export function ConcentrationScreen({ portfolioId, concentrationId }: { portfolioId: string; concentrationId: string }) {
  const loaded = useLoaded(`${portfolioId}/${concentrationId}`, () => api.concentration(portfolioId, concentrationId));
  return (
    <>
      <Header current={3} portfolioId={portfolioId} />
      {loaded.state === "loading" && <main className="page loading">Tracing ownership and Registrations…</main>}
      {loaded.state === "failed" &&
        (loaded.error instanceof NotFound ? (
          <main className="page">
            <div className="card" style={{ padding: "28px 32px" }} role="status">
              <h1 style={{ fontSize: 24 }}>This concentration no longer holds.</h1>
              <p style={{ marginTop: 10, fontSize: 16, color: "var(--text-2)" }}>
                A Verdict removed a match it rested on. <a href={href.exposure(portfolioId)}>Back to your exposure</a>
              </p>
            </div>
          </main>
        ) : (
          <main className="page"><Failure error={loaded.error} /></main>
        ))}
      {loaded.state === "ready" && <DetailView detail={loaded.value} portfolioId={portfolioId} reload={loaded.reload} />}
    </>
  );
}
