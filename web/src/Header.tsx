import { NotFound } from "./api";
import { href } from "./route";

type Step = 1 | 2 | 3;

const STEPS: { step: Step; name: string }[] = [
  { step: 1, name: "Portfolio" },
  { step: 2, name: "Exposure" },
  { step: 3, name: "Concentration" },
];

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="#17496B" strokeWidth="2" aria-hidden="true">
      <path d="M2 6.5l2.5 2.5L10 3.5" />
    </svg>
  );
}

/** The brand and the three steps; a step already passed links back to its screen. */
export function Header({ current, portfolioId }: { current: Step; portfolioId?: string }) {
  const stepHref = (step: Step) =>
    portfolioId && step < current ? (step === 1 ? href.portfolio(portfolioId) : href.exposure(portfolioId)) : null;
  return (
    <header className="header">
      <a className="brand" href={href.landing()}>
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="#1D5C86" strokeWidth="2" aria-hidden="true">
          <circle cx="7" cy="15" r="4" />
          <circle cx="15" cy="15" r="4" />
          <circle cx="11" cy="6" r="4" />
        </svg>
        Common Cause
      </a>
      <nav aria-label="Steps">
        <ol className="steps">
          {STEPS.map(({ step, name }) => {
            const link = stepHref(step);
            const content = (
              <>
                <span className="step-dot">{step < current ? <CheckIcon /> : step}</span>
                {name}
              </>
            );
            const className = `step${step < current ? " step-done" : ""}`;
            return (
              <li key={step} className="row">
                {step > 1 && <span className="step-rule" aria-hidden="true" />}
                {link ? (
                  <a className={className} href={link}>
                    {content}
                  </a>
                ) : (
                  <span className={className} aria-current={step === current ? "step" : undefined}>
                    {content}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
      <div className="header-spacer" />
    </header>
  );
}

export function ArrowIcon({ color = "#FFFFFF" }: { color?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke={color} strokeWidth="2" aria-hidden="true">
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  );
}

export function Failure({ error }: { error: unknown }) {
  if (error instanceof NotFound) {
    return (
      <div className="error" role="alert">
        There is nothing at this address any more. <a href={href.landing()}>Start from your list of names</a>.
      </div>
    );
  }
  return (
    <div className="error" role="alert">
      Something went wrong talking to the server: {error instanceof Error ? error.message : String(error)}
    </div>
  );
}
