"""HTTP API over the graph: Portfolio intake, Verdicts and Hidden Concentrations; and the interface, once built."""

import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common_cause.exposure.graph import ConcentrationDetail, Exposure, Graph, Member, PortfolioMember
from common_cause.ingest.snapshot import DEFAULT_SNAPSHOT_DIR
from common_cause.sample import BASELINE_DESCRIPTION, BASELINE_MEMBERS, SAMPLE_DESCRIPTION, SAMPLE_MEMBERS

# Portfolios and Verdicts; not committed.
DEFAULT_WORKSPACE_PATH = DEFAULT_SNAPSHOT_DIR.parent / "workspace.duckdb"

# Where `make web` builds the interface.
DEFAULT_WEB_DIR = Path(__file__).resolve().parents[3] / "web" / "dist"


class MemberIn(BaseModel):
    name: Annotated[str, Field(min_length=1)]
    state: str | None = None
    city: str | None = None

    def member(self) -> Member:
        return Member(self.name, self.state, self.city)


class PortfolioIn(BaseModel):
    members: Annotated[list[MemberIn], Field(min_length=1)]
    sample: bool = False


class Portfolio(BaseModel):
    portfolio_id: str
    sample: bool
    members: list[PortfolioMember]


class VerdictIn(BaseModel):
    verdict: Literal["confirmed", "rejected"]


class Baseline(BaseModel):
    """What a random Portfolio of the same size finds, to set beside the curated sample."""

    description: str
    members: list[MemberIn]
    matched: int
    unverifiable: int
    # Firm Hidden Concentrations other than a shared jurisdiction, and the members firmly in one: the terms the
    # sample's own headline figures use.
    concentrations: int
    affected: int


class Sample(BaseModel):
    description: str
    members: list[MemberIn]
    baseline: Baseline


def create_app(
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    workspace_path: Path = DEFAULT_WORKSPACE_PATH,
    web_dir: Path = DEFAULT_WEB_DIR,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.graph = Graph.open(snapshot_dir, workspace_path)
        yield
        app.state.graph.close()

    app = FastAPI(title="Common Cause", lifespan=lifespan)
    baseline: list[Baseline] = []
    baseline_lock = threading.Lock()

    def graph(request: Request) -> Graph:
        return request.app.state.graph

    def portfolio(request: Request, portfolio_id: str) -> Portfolio:
        g = graph(request)
        return Portfolio(portfolio_id=portfolio_id, sample=g.is_sample(portfolio_id), members=g.portfolio(portfolio_id))

    def member(request: Request, portfolio_id: str, member_id: int) -> PortfolioMember:
        return next(m for m in graph(request).portfolio(portfolio_id) if m.member_id == member_id)

    @app.post("/portfolios", status_code=201)
    def create_portfolio(body: PortfolioIn, request: Request) -> Portfolio:
        portfolio_id = graph(request).create_portfolio([m.member() for m in body.members], sample=body.sample)
        return portfolio(request, portfolio_id)

    @app.get("/portfolios/{portfolio_id}")
    def read_portfolio(portfolio_id: str, request: Request) -> Portfolio:
        with _not_found():
            return portfolio(request, portfolio_id)

    @app.put("/portfolios/{portfolio_id}/members/{member_id}")
    def update_member(portfolio_id: str, member_id: int, body: MemberIn, request: Request) -> PortfolioMember:
        with _not_found():
            graph(request).update_member(portfolio_id, member_id, body.member())
            return member(request, portfolio_id, member_id)

    @app.put("/portfolios/{portfolio_id}/members/{member_id}/verdicts/{entity_id}")
    def record_verdict(
        portfolio_id: str, member_id: int, entity_id: str, body: VerdictIn, request: Request
    ) -> PortfolioMember:
        with _not_found():
            graph(request).record_verdict(portfolio_id, member_id, entity_id, body.verdict)
            return member(request, portfolio_id, member_id)

    @app.delete("/portfolios/{portfolio_id}/members/{member_id}/verdicts/{entity_id}")
    def clear_verdict(portfolio_id: str, member_id: int, entity_id: str, request: Request) -> PortfolioMember:
        with _not_found():
            graph(request).clear_verdict(portfolio_id, member_id, entity_id)
            return member(request, portfolio_id, member_id)

    @app.get("/portfolios/{portfolio_id}/exposure")
    def exposure(portfolio_id: str, request: Request) -> Exposure:
        with _not_found():
            return graph(request).exposure(portfolio_id)

    @app.get("/portfolios/{portfolio_id}/concentrations/{concentration_id}")
    def concentration(portfolio_id: str, concentration_id: str, request: Request) -> ConcentrationDetail:
        with _not_found():
            return graph(request).concentration(portfolio_id, concentration_id)

    @app.get("/sample")
    def sample(request: Request) -> Sample:
        # The random Portfolio is matched once per process, the first time anyone asks.
        with baseline_lock:
            if not baseline:
                g = graph(request)
                result = g.exposure(g.create_portfolio(BASELINE_MEMBERS))
                baseline.append(
                    Baseline(
                        description=BASELINE_DESCRIPTION,
                        members=[_member_in(m) for m in BASELINE_MEMBERS],
                        matched=result.ownership.matched,
                        unverifiable=result.ownership.unverifiable,
                        concentrations=sum(c.kind != "Jurisdiction" and not c.tentative for c in result.concentrations),
                        affected=result.affected,
                    )
                )
        return Sample(
            description=SAMPLE_DESCRIPTION, members=[_member_in(m) for m in SAMPLE_MEMBERS], baseline=baseline[0]
        )

    if (web_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


def _member_in(member: Member) -> MemberIn:
    return MemberIn(name=member.name, state=member.state, city=member.city)


@contextmanager
def _not_found() -> Iterator[None]:
    try:
        yield
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
