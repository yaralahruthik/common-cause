import { useState } from "react";
import { api, type Exposure, type Match, type MemberOwnership, type Portfolio, type PortfolioMember } from "../api";
import { ArrowIcon, Failure, Header } from "../Header";
import { useLoaded } from "../load";
import { formatMember, parseNames } from "../parse";
import { groupMembers, type NotFound, place, recordLabel, recordSource, recordUrl, type Undecided } from "../portfolio";
import { href } from "../route";

type Act = (memberId: number, action: () => Promise<unknown>) => Promise<void>;

export function SampleBanner() {
  return (
    <div className="banner">
      <div className="banner-inner">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="#8A4F00" strokeWidth="1.6" aria-hidden="true">
          <circle cx="9" cy="9" r="7.5" />
          <path d="M9 5v5M9 12.5v.5" />
        </svg>
        <span>
          <strong>Sample Portfolio.</strong> 15 food and beverage makers that run their own trucks, chosen because they
          are in the data. A random list is shown beside the result on the next step.
        </span>
        <a href={href.landing()}>Use my own names</a>
      </div>
    </div>
  );
}

function Ids({ records }: { records: string[] }) {
  return (
    <span className="mono muted" style={{ fontSize: 12 }}>
      {records.map((r, i) => (
        <span key={r}>
          {i > 0 && " · "}
          <a href={recordUrl(r)} target="_blank" rel="noreferrer" style={{ color: "inherit" }}>
            {recordLabel(r)}
          </a>
        </span>
      ))}
    </span>
  );
}

function DecisionCard({ undecided, portfolioId, act, busy }: { undecided: Undecided; portfolioId: string; act: Act; busy: boolean }) {
  const { member, candidates } = undecided;
  const judge = (match: Match, verdict: "confirmed" | "rejected") =>
    act(member.member_id, () => api.recordVerdict(portfolioId, member.member_id, match.entity_id, verdict));
  return (
    <article className="card decision" aria-label={`Decide on ${member.name}`}>
      <div className="decision-name">
        <div className="muted" style={{ fontSize: 13 }}>You entered</div>
        <div style={{ fontSize: 19, fontWeight: 700, lineHeight: 1.3 }}>{formatMember(member)}</div>
        <div className="muted" style={{ fontSize: 14, lineHeight: 1.5 }}>
          {candidates.length === 1
            ? "One registry record comes close to this name. Is it the one you mean?"
            : `${candidates.length} registry records come close to this name. Pick the one you mean.`}
        </div>
      </div>
      <div className="stack" style={{ gap: 0 }}>
        {candidates.map((c) => (
          <div className="candidate" key={c.entity_id}>
            <div className="stack" style={{ gap: 4 }}>
              <div className="row" style={{ gap: 10, alignItems: "baseline" }}>
                <span style={{ fontWeight: 600, fontSize: 16 }}>{c.name}</span>
                <span className="muted" style={{ fontSize: 14 }}>{place(c.city, c.state)}</span>
              </div>
              <div className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>
                {recordSource(c.record_id)} · <Ids records={c.entity_records} />
              </div>
              <div className="muted" style={{ fontSize: 13 }}>{c.evidence}</div>
            </div>
            <div className="row" style={{ gap: 8 }}>
              <button type="button" className="btn btn-outline btn-small" disabled={busy} onClick={() => judge(c, "confirmed")}>
                This is it
              </button>
              <button type="button" className="btn btn-secondary btn-small" disabled={busy} onClick={() => judge(c, "rejected")}>
                Not this
              </button>
            </div>
          </div>
        ))}
        {candidates.length > 1 && (
          <div style={{ padding: "12px 24px" }}>
            <button
              type="button"
              className="link-button"
              disabled={busy}
              onClick={() =>
                act(member.member_id, () =>
                  Promise.all(candidates.map((c) => api.recordVerdict(portfolioId, member.member_id, c.entity_id, "rejected"))),
                )
              }
            >
              None of these is right
            </button>
          </div>
        )}
      </div>
    </article>
  );
}

function NotFoundRow({ row, portfolioId, act, busy }: { row: NotFound; portfolioId: string; act: Act; busy: boolean }) {
  const { member, rejected } = row;
  const [text, setText] = useState(formatMember(member));
  const inputId = `retry-${member.member_id}`;
  return (
    <form
      className="table-row notfound-grid"
      onSubmit={(event) => {
        event.preventDefault();
        const [corrected] = parseNames(text);
        if (corrected) void act(member.member_id, () => api.updateMember(portfolioId, member.member_id, corrected));
      }}
    >
      <div className="stack" style={{ gap: 4 }}>
        <span className="muted" style={{ fontSize: 13 }}>You entered</span>
        <span style={{ fontSize: 16, fontWeight: 600 }}>{formatMember(member)}</span>
      </div>
      {rejected.length ? (
        <span style={{ fontSize: 14, color: "var(--text-2)", lineHeight: 1.5 }}>
          You rejected{" "}
          {rejected.map((m, i) => (
            <span key={m.entity_id}>
              {i > 0 && (i === rejected.length - 1 ? " and " : ", ")}
              <strong>{m.name}</strong> <span className="mono" style={{ fontSize: 13 }}>{recordLabel(m.record_id)}</span>
            </span>
          ))}
          . It no longer counts toward any concentration in this Portfolio.
        </span>
      ) : (
        <span style={{ fontSize: 14, color: "var(--text-2)" }}>
          No record in GLEIF or the FMCSA census has this name or one close to it.
        </span>
      )}
      <div className="row" style={{ gap: 8, alignItems: "flex-end" }}>
        <div className="field">
          <label htmlFor={inputId}>Name, then a state or city</label>
          <input id={inputId} value={text} onChange={(event) => setText(event.target.value)} />
        </div>
        <button type="submit" className="btn btn-outline btn-small" disabled={busy || !text.trim()}>
          Search again
        </button>
        {rejected.length > 0 && (
          <button
            type="button"
            className="btn-quiet"
            style={{ fontSize: 14, color: "var(--text-2)" }}
            disabled={busy}
            onClick={() =>
              act(member.member_id, () =>
                Promise.all(rejected.map((m) => api.clearVerdict(portfolioId, member.member_id, m.entity_id))),
              )
            }
          >
            Undo
          </button>
        )}
      </div>
    </form>
  );
}

function OwnershipCell({ ownership }: { ownership: MemberOwnership | undefined }) {
  if (!ownership?.status) return <span className="muted">Not known yet</span>;
  if (ownership.status === "Undisclosed Parent") return <span className="owner-hidden">Owner not visible</span>;
  return <span style={{ fontSize: 13, color: "var(--text-2)" }}>{ownership.status}</span>;
}

export function heading(matched: number, total: number, undecided: number): string {
  const found = `${matched} of ${total} ${total === 1 ? "name" : "names"} matched.`;
  if (undecided === 0) return found;
  return `${found} ${undecided} ${undecided === 1 ? "needs" : "need"} your decision.`;
}

function PortfolioView({ portfolio, exposure, reload }: { portfolio: Portfolio; exposure: Exposure; reload: () => Promise<void> }) {
  const [busyMember, setBusyMember] = useState<number | null>(null);
  const [problem, setProblem] = useState<unknown>(null);
  const { matched, decide, notFound } = groupMembers(portfolio.members);
  const ownership = new Map(exposure.ownership.members.map((m) => [m.member_id, m]));
  const id = portfolio.portfolio_id;

  const act: Act = async (memberId, action) => {
    setBusyMember(memberId);
    setProblem(null);
    try {
      await action();
      await reload();
    } catch (error) {
      setProblem(error);
    } finally {
      setBusyMember(null);
    }
  };
  const reject = (member: PortfolioMember, match: Match) =>
    act(member.member_id, () => api.recordVerdict(id, member.member_id, match.entity_id, "rejected"));

  return (
    <>
      {portfolio.sample && <SampleBanner />}
      <main className="page">
        <div className="stack">
          <div className="eyebrow">Step 1 of 3 · Portfolio</div>
          <h1 className="title">{heading(matched.length, portfolio.members.length, decide.length)}</h1>
          <p className="lede">
            {decide.length
              ? <>You can go on without deciding. Any finding that depends on an undecided name is marked <em>tentative</em>.</>
              : "Check the matches below. If one is wrong, reject it and it stops counting toward your exposure."}
          </p>
        </div>
        {problem !== null && <Failure error={problem} />}

        {decide.length > 0 && (
          <section className="stack-16" aria-labelledby="decide-title">
            <h2 id="decide-title" className="section-title">
              Needs your decision <span className="count-chip amber">{decide.length}</span>
            </h2>
            {decide.map((u) => (
              <DecisionCard key={u.member.member_id} undecided={u} portfolioId={id} act={act} busy={busyMember === u.member.member_id} />
            ))}
          </section>
        )}

        {notFound.length > 0 && (
          <section className="stack-16" aria-labelledby="notfound-title">
            <h2 id="notfound-title" className="section-title">
              Not found <span className="count-chip">{notFound.length}</span>
            </h2>
            <p style={{ fontSize: 15, color: "var(--text-2)" }}>
              These count as unmatched. Fix the spelling or add a state, then search again.
            </p>
            <div className="card table">
              {notFound.map((row) => (
                <NotFoundRow
                  key={`${row.member.member_id}:${formatMember(row.member)}`}
                  row={row}
                  portfolioId={id}
                  act={act}
                  busy={busyMember === row.member.member_id}
                />
              ))}
            </div>
          </section>
        )}

        {matched.length > 0 && (
          <section className="stack-16" aria-labelledby="matched-title">
            <h2 id="matched-title" className="section-title">
              Matched <span className="count-chip blue">{matched.length}</span>
            </h2>
            <div className="card table" role="table" aria-labelledby="matched-title">
              <div className="table-head matched-grid" role="row">
                <span role="columnheader">You entered</span>
                <span role="columnheader">Matched to</span>
                <span role="columnheader">Why</span>
                <span role="columnheader">Ownership</span>
                <span role="columnheader"><span className="visually-hidden">Reject</span></span>
              </div>
              {matched.map(({ member, match }) => (
                <div className="table-row matched-grid" role="row" key={member.member_id}>
                  <span role="cell" style={{ fontWeight: 600 }}>{formatMember(member)}</span>
                  <span role="cell" className="stack" style={{ gap: 2 }}>
                    <span>{match.name}</span>
                    <Ids records={match.entity_records} />
                  </span>
                  <span role="cell" className="muted" style={{ fontSize: 13 }}>
                    {match.verdict === "confirmed" ? "You confirmed this match" : match.evidence}
                  </span>
                  <span role="cell"><OwnershipCell ownership={ownership.get(member.member_id)} /></span>
                  <span role="cell">
                    <button
                      type="button"
                      className="btn-quiet"
                      aria-label={`Reject the match of ${member.name} to ${match.name}`}
                      disabled={busyMember === member.member_id}
                      onClick={() => reject(member, match)}
                    >
                      Wrong?
                    </button>
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
      <div className="footer-bar">
        <div className="footer-inner">
          <span>
            {decide.length
              ? `${decide.length} undecided ${decide.length === 1 ? "name" : "names"} will be treated as unconfirmed.`
              : notFound.length
                ? `${notFound.length} ${notFound.length === 1 ? "name is" : "names are"} left out until found.`
                : "Every name is matched."}
          </span>
          <a className="btn btn-primary" href={href.exposure(id)}>
            See your exposure <ArrowIcon />
          </a>
        </div>
      </div>
    </>
  );
}

export function PortfolioScreen({ portfolioId }: { portfolioId: string }) {
  const loaded = useLoaded(portfolioId, () => Promise.all([api.portfolio(portfolioId), api.exposure(portfolioId)]));
  return (
    <>
      <Header current={1} portfolioId={portfolioId} />
      {loaded.state === "loading" && <main className="page loading">Matching your names…</main>}
      {loaded.state === "failed" && (
        <main className="page"><Failure error={loaded.error} /></main>
      )}
      {loaded.state === "ready" && (
        <PortfolioView portfolio={loaded.value[0]} exposure={loaded.value[1]} reload={loaded.reload} />
      )}
    </>
  );
}
