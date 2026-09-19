from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pipishrimp-backend"}


def test_opportunity_list_is_typed_and_ranked() -> None:
    response = client.get("/v1/opportunities")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 3
    assert items[0]["bcop_score"] >= items[1]["bcop_score"]
    assert all(item["is_sample"] is True for item in items)
    required_fields = {
        "id", "project_id", "title", "category", "source_url", "source_type", "evidence_level",
        "capital_required_usd", "estimated_human_minutes", "reward_type", "reward_certainty", "deadline",
        "risk_level", "score_components", "bcop_score", "recommended_action", "fetched_at", "is_sample", "summary",
    }
    assert all(required_fields <= item.keys() for item in items)


def test_opportunity_filters_and_detail() -> None:
    response = client.get("/v1/opportunities", params={"risk_level": "high"})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["sample-unverified-claim"]

    detail = client.get("/v1/opportunities/sample-mobile-docs")
    assert detail.status_code == 200
    assert detail.json()["title"].startswith("Sample:")


def test_missing_opportunity_returns_404() -> None:
    response = client.get("/v1/opportunities/missing")

    assert response.status_code == 404
