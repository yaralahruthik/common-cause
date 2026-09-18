"""HTTP API over the graph: Portfolio intake, Verdicts and Hidden Concentrations."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from common_cause.exposure.graph import Exposure, Graph, Member, PortfolioMember
from common_cause.ingest.snapshot import DEFAULT_SNAPSHOT_DIR

# Portfolios and Verdicts; not committed.
DEFAULT_WORKSPACE_PATH = DEFAULT_SNAPSHOT_DIR.parent / "workspace.duckdb"


class MemberIn(BaseModel):
    name: Annotated[str, Field(min_length=1)]
    state: str | None = None
    city: str | None = None


class PortfolioIn(BaseModel):
    members: Annotated[list[MemberIn], Field(min_length=1)]


class Portfolio(BaseModel):
    portfolio_id: str
    members: list[PortfolioMember]


class VerdictIn(BaseModel):
    verdict: Literal["confirmed", "rejected"]


def create_app(snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR, workspace_path: Path = DEFAULT_WORKSPACE_PATH) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.graph = Graph.open(snapshot_dir, workspace_path)
        yield
        app.state.graph.close()

    app = FastAPI(title="Common Cause", lifespan=lifespan)

    def graph(request: Request) -> Graph:
        return request.app.state.graph

    @app.post("/portfolios", status_code=201)
    def create_portfolio(body: PortfolioIn, request: Request) -> Portfolio:
        portfolio_id = graph(request).create_portfolio([Member(m.name, m.state, m.city) for m in body.members])
        return Portfolio(portfolio_id=portfolio_id, members=graph(request).portfolio(portfolio_id))

    @app.get("/portfolios/{portfolio_id}")
    def read_portfolio(portfolio_id: str, request: Request) -> Portfolio:
        with _not_found():
            return Portfolio(portfolio_id=portfolio_id, members=graph(request).portfolio(portfolio_id))

    @app.put("/portfolios/{portfolio_id}/members/{member_id}/verdicts/{entity_id}")
    def record_verdict(
        portfolio_id: str, member_id: int, entity_id: str, body: VerdictIn, request: Request
    ) -> PortfolioMember:
        with _not_found():
            graph(request).record_verdict(portfolio_id, member_id, entity_id, body.verdict)
            return next(m for m in graph(request).portfolio(portfolio_id) if m.member_id == member_id)

    @app.get("/portfolios/{portfolio_id}/exposure")
    def exposure(portfolio_id: str, request: Request) -> Exposure:
        with _not_found():
            return graph(request).exposure(portfolio_id)

    return app


@contextmanager
def _not_found() -> Iterator[None]:
    try:
        yield
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
