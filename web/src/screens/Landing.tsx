import { type ChangeEvent, useRef, useState } from "react";
import { api } from "../api";
import { baselineSummary } from "../exposure";
import { ArrowIcon, Failure, Header } from "../Header";
import { useLoaded } from "../load";
import { formatMember, parseCsv, parseNames } from "../parse";
import { href, navigate } from "../route";

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function Landing() {
  const [text, setText] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [problem, setProblem] = useState<unknown>(null);
  const [busy, setBusy] = useState<"names" | "sample" | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const sample = useLoaded("sample", api.sample);
  const names = parseNames(text);

  async function start(members: ReturnType<typeof parseNames>, isSample: boolean) {
    setBusy(isSample ? "sample" : "names");
    setProblem(null);
    try {
      const portfolio = await api.createPortfolio(members, isSample);
      navigate(href.portfolio(portfolio.portfolio_id));
    } catch (error) {
      setProblem(error);
      setBusy(null);
    }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    const read = parseCsv(await chosen.text());
    if (!read.length) {
      setMessage(`No names found in ${chosen.name}. It needs a column headed "name", or names in the first column.`);
      return;
    }
    setText(read.map(formatMember).join("\n"));
    setMessage(`Read ${read.length} names from ${chosen.name}. Check them, then find these companies.`);
  }

  return (
    <>
      <Header current={1} />
      <main className="landing">
        <section className="stack" style={{ gap: 28 }}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="eyebrow">Step 1 of 3</div>
            <h1>Which suppliers and carriers do you rely on?</h1>
            <p className="lede" style={{ fontSize: 18, maxWidth: 620 }}>
              List them by name. We find each one in public registries, then show you which of them look independent
              but would fail together.
            </p>
          </div>
          <form
            className="stack-16"
            onSubmit={(event) => {
              event.preventDefault();
              if (names.length) void start(names, false);
              else setMessage("Add at least one name, one per line.");
            }}
          >
            <div className="stack" style={{ gap: 8 }}>
              <label htmlFor="names" style={{ fontSize: 14, fontWeight: 600 }}>
                One name per line. Add a state or city after a comma if you know it.
              </label>
              <textarea
                id="names"
                className="names-input"
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder={"Prairie Farms Dairy, IL\nKoch Foods LLC, TN\nHerr Foods Inc, Nottingham PA"}
                aria-describedby="names-status"
              />
              <div id="names-status" className="muted" style={{ fontSize: 14, minHeight: 20 }} aria-live="polite">
                {message ?? (names.length ? `${names.length} ${names.length === 1 ? "name" : "names"}` : "")}
              </div>
            </div>
            <div className="row">
              <button type="submit" className="btn btn-primary" disabled={busy !== null}>
                {busy === "names" ? "Finding them…" : "Find these companies"}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => file.current?.click()}>
                Upload a CSV
              </button>
              <input ref={file} type="file" accept=".csv,text/csv" hidden onChange={upload} />
            </div>
          </form>
          {problem !== null && <Failure error={problem} />}
          <div className="card sample-card">
            <div className="stack" style={{ gap: 6 }}>
              <h2 style={{ fontSize: 17 }}>No list at hand? See a sample.</h2>
              <p style={{ fontSize: 14, lineHeight: 1.5, color: "var(--text-2)" }}>
                {sample.state === "ready"
                  ? `${sample.value.description} ${capitalise(baselineSummary(sample.value.baseline))}, and we show that beside the result.`
                  : "15 food and beverage makers that run their own trucks, chosen because they are in the data."}
              </p>
            </div>
            <button
              type="button"
              className="btn btn-outline"
              disabled={sample.state !== "ready" || busy !== null}
              onClick={() => sample.state === "ready" && void start(sample.value.members, true)}
            >
              {busy === "sample" ? "Opening…" : "Open the sample"}
              <ArrowIcon color="#1D5C86" />
            </button>
          </div>
          {sample.state === "failed" && <Failure error={sample.error} />}
        </section>
        <aside className="stack" style={{ gap: 24, paddingTop: 40 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }} className="muted">
            What happens next
          </div>
          <ol className="next-steps">
            <li>
              <span className="mono" style={{ color: "var(--accent)" }}>1</span>
              <span>
                <strong>We match each name</strong> to company records in GLEIF and the FMCSA carrier census. Where we
                are unsure, you decide.
              </span>
            </li>
            <li>
              <span className="mono" style={{ color: "var(--accent)" }}>2</span>
              <span>
                <strong>We show your exposure</strong>: groups of names that share an owner, an address or a
                jurisdiction.
              </span>
            </li>
            <li>
              <span className="mono" style={{ color: "var(--accent)" }}>3</span>
              <span>
                <strong>You open any group</strong> to see the ownership path, their trucks and the source records.
              </span>
            </li>
          </ol>
          <p className="muted" style={{ borderTop: "1px solid var(--line)", paddingTop: 18, fontSize: 13, lineHeight: 1.55 }}>
            Public records only: GLEIF, which says who owns whom, and the FMCSA carrier census, which lists companies
            that run trucks.
          </p>
        </aside>
      </main>
    </>
  );
}
