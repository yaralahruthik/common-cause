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
        {"lei": "SUB", "name": "Brandco Foods LLC", "jurisdiction": None},
        {"lei": "HOLD", "name": "Acme Holdings Inc", "jurisdiction": None},
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


def test_a_concentration_is_read_on_its_own_and_undoing_a_verdict_brings_it_back(client):
    portfolio_id = client.post(
        "/portfolios", json={"members": [{"name": "Acme Holdings"}, {"name": "Brandco Foods"}]}
    ).json()["portfolio_id"]
    [concentration] = client.get(f"/portfolios/{portfolio_id}/exposure").json()["concentrations"]
    detail_url = f"/portfolios/{portfolio_id}/concentrations/{concentration['id']}"

    detail = client.get(detail_url)

    assert detail.status_code == 200
    assert [m["path"][-1]["lei"] for m in detail.json()["members"]] == ["HOLD", "HOLD"]
    verdict_url = f"/portfolios/{portfolio_id}/members/2/verdicts/gleif:SUB"
    client.put(verdict_url, json={"verdict": "rejected"})
    assert client.get(detail_url).status_code == 404
    undone = client.delete(verdict_url)
    assert (undone.status_code, undone.json()["matches"][0]["verdict"]) == (200, None)
    assert client.get(detail_url).status_code == 200
    assert client.get(f"/portfolios/{portfolio_id}/concentrations/nope").status_code == 404


def test_a_member_is_searched_again_under_a_corrected_name(client):
    portfolio_id = client.post("/portfolios", json={"members": [{"name": "Brandko Fodes"}]}).json()["portfolio_id"]

    corrected = client.put(f"/portfolios/{portfolio_id}/members/1", json={"name": "Brandco Foods", "state": ""})

    assert corrected.status_code == 200
    assert [(m["entity_id"], m["band"]) for m in corrected.json()["matches"]] == [("gleif:SUB", "Firm")]
    assert client.put(f"/portfolios/{portfolio_id}/members/7", json={"name": "Acme"}).status_code == 404


def test_the_sample_portfolio_comes_with_a_random_portfolio_to_compare_it_with(client):
    sample = client.get("/sample").json()

    assert len(sample["members"]) == 15
    baseline = sample["baseline"]
    assert (len(baseline["members"]), baseline["affected"], baseline["concentrations"]) == (15, 0, 0)
    created = client.post("/portfolios", json={"members": sample["members"], "sample": True}).json()
    assert created["sample"] is True
    assert client.get(f"/portfolios/{created['portfolio_id']}").json()["sample"] is True
    own = client.post("/portfolios", json={"members": [{"name": "Acme Holdings"}]}).json()
    assert own["sample"] is False


def test_the_interface_is_served_beside_the_api_when_it_has_been_built(tmp_path):
    sources = RawSourceBuilder()
    sources.lei_record("HOLD", "Acme Holdings Inc")
    web_dir = tmp_path / "dist"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("<title>Common Cause</title>")
    app = create_app(built_snapshot(sources, tmp_path), tmp_path / "workspace.duckdb", web_dir=web_dir)

    with TestClient(app) as client:
        assert "Common Cause" in client.get("/").text
        assert client.get("/portfolios/nope").status_code == 404
