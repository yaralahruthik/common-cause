from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from common_cause.api import create_app

from .raw_sources import RawSourceBuilder
from .snapshots import built_snapshot


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    sources = RawSourceBuilder()
    for lei, name in [("HOLD", "Acme Holdings Inc"), ("SUB", "Brandco Foods LLC")]:
        sources.lei_record(lei, name, **{"Entity.HeadquartersAddress.FirstAddressLine": f"{lei} Commerce Drive"})
    sources.relationship("SUB", "HOLD", "IS_DIRECTLY_CONSOLIDATED_BY")
    app = create_app(built_snapshot(sources, tmp_path), tmp_path / "workspace.duckdb")
    with TestClient(app) as client:
        yield client


def test_a_portfolio_is_matched_judged_and_its_exposure_reported(client):
    created = client.post(
        "/portfolios", json={"members": [{"name": "Acme Holdings"}, {"name": "Brandco Foods", "state": ""}]}
    )
    assert created.status_code == 201
    portfolio = created.json()
    assert [[m["entity_id"] for m in member["matches"]] for member in portfolio["members"]] == [
        ["gleif:HOLD"],
        ["gleif:SUB"],
    ]
    exposure_url = f"/portfolios/{portfolio['portfolio_id']}/exposure"
    exposure = client.get(exposure_url).json()
    assert [(c["kind"], c["label"], c["tentative"]) for c in exposure["concentrations"]] == [
        ("Ultimate Parent", "Acme Holdings Inc", False)
    ]
    assert exposure["concentrations"][0]["members"][1]["path"] == [
        {"lei": "SUB", "name": "Brandco Foods LLC"},
        {"lei": "HOLD", "name": "Acme Holdings Inc"},
    ]
    assert exposure["as_of"]["GLEIF"] == "2026-09-18"

    judged = client.put(
        f"/portfolios/{portfolio['portfolio_id']}/members/2/verdicts/gleif:SUB", json={"verdict": "rejected"}
    )

    assert judged.status_code == 200
    assert judged.json()["matches"][0]["verdict"] == "rejected"
    assert client.get(exposure_url).json()["concentrations"] == []
    assert client.get(f"/portfolios/{portfolio['portfolio_id']}").json()["members"][1]["matches"][0]["verdict"] == (
        "rejected"
    )


def test_unknown_portfolios_members_and_matches_are_not_found(client):
    portfolio_id = client.post("/portfolios", json={"members": [{"name": "Acme Holdings"}]}).json()["portfolio_id"]

    assert client.get("/portfolios/nope").status_code == 404
    assert client.get("/portfolios/nope/exposure").status_code == 404
    verdict = {"verdict": "confirmed"}
    assert client.put(f"/portfolios/{portfolio_id}/members/9/verdicts/gleif:HOLD", json=verdict).status_code == 404
    assert client.put(f"/portfolios/{portfolio_id}/members/1/verdicts/gleif:SUB", json=verdict).status_code == 404


def test_a_verdict_must_confirm_or_reject_and_a_portfolio_needs_a_member(client):
    portfolio_id = client.post("/portfolios", json={"members": [{"name": "Acme Holdings"}]}).json()["portfolio_id"]

    maybe = client.put(f"/portfolios/{portfolio_id}/members/1/verdicts/gleif:HOLD", json={"verdict": "maybe"})

    assert maybe.status_code == 422
    assert client.post("/portfolios", json={"members": []}).status_code == 422
