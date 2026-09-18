import { useEffect, useState } from "react";

export type Route =
  | { screen: "landing" }
  | { screen: "portfolio"; portfolioId: string }
  | { screen: "exposure"; portfolioId: string }
  | { screen: "concentration"; portfolioId: string; concentrationId: string };

/** Screens live in the URL hash, so a reload or a shared link opens the same screen. */
export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  const [root, portfolioId, view, concentrationId] = parts;
  if (root !== "portfolios" || !portfolioId) return { screen: "landing" };
  if (view === "exposure") return { screen: "exposure", portfolioId };
  if (view === "concentrations" && concentrationId) return { screen: "concentration", portfolioId, concentrationId };
  return { screen: "portfolio", portfolioId };
}

export const href = {
  landing: () => "#/",
  portfolio: (portfolioId: string) => `#/portfolios/${encodeURIComponent(portfolioId)}`,
  exposure: (portfolioId: string) => `#/portfolios/${encodeURIComponent(portfolioId)}/exposure`,
  concentration: (portfolioId: string, concentrationId: string) =>
    `#/portfolios/${encodeURIComponent(portfolioId)}/concentrations/${encodeURIComponent(concentrationId)}`,
};

export function navigate(to: string): void {
  window.location.hash = to;
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const changed = () => {
      setRoute(parseRoute(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return route;
}
