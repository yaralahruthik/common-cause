import { describe, expect, it } from "vitest";
import { href, parseRoute } from "./route";

describe("parseRoute", () => {
  it("reads every screen back from the link that leads to it", () => {
    expect(parseRoute(href.landing())).toEqual({ screen: "landing" });
    expect(parseRoute(href.portfolio("p1"))).toEqual({ screen: "portfolio", portfolioId: "p1" });
    expect(parseRoute(href.exposure("p1"))).toEqual({ screen: "exposure", portfolioId: "p1" });
    expect(parseRoute(href.concentration("p1", "c9"))).toEqual({
      screen: "concentration",
      portfolioId: "p1",
      concentrationId: "c9",
    });
  });

  it("opens the landing page for anything it does not know", () => {
    expect(parseRoute("")).toEqual({ screen: "landing" });
    expect(parseRoute("#/elsewhere")).toEqual({ screen: "landing" });
  });
});
