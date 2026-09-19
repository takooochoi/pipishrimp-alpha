from datetime import datetime, timezone

import pytest

from app.ingestion import NormalizedOpportunity, ReviewState, ingest_opportunity
from app.review_store import ReviewStore, ReviewStoreError


RETRIEVED_AT = datetime(2026, 9, 18, 12, 5, tzinfo=timezone.utc)


def record(stable_id: str = "store-001", *, title: str = "Stored candidate") -> NormalizedOpportunity:
    return ingest_opportunity(
        {
            "stable_id": stable_id,
            "title": title,
            "summary": "A normalized candidate retained for explicit human review.",
            "official_publisher": "Solana Mobile",
            "source_id": "solana_mobile_docs",
            "source_url": "https://docs.solanamobile.com/opportunities",
            "evidence_label": "Project claim",
            "deadline": "2026-10-01",
            "cost": None,
        },
        retrieved_at=RETRIEVED_AT,
        now=RETRIEVED_AT,
    )


def test_store_survives_restart_and_new_records_are_pending(tmp_path) -> None:
    db_path = tmp_path / "review.sqlite3"

    with ReviewStore(db_path) as store:
        stored = store.add(record())
        assert stored.review_state is ReviewState.NEEDS_REVIEW
        assert stored.externally_publishable is False

    with ReviewStore(db_path) as restarted:
        restored = restarted.get("store-001")
        assert restored is not None
        assert restored.model_dump(mode="json") == stored.model_dump(mode="json")
        assert len(restarted.list(state=ReviewState.NEEDS_REVIEW)) == 1


def test_duplicate_requires_explicit_update_path(tmp_path) -> None:
    db_path = tmp_path / "review.sqlite3"
    with ReviewStore(db_path) as store:
        store.add(record())
        with pytest.raises(ReviewStoreError, match="duplicate_stable_id"):
            store.add(record(title="Silent overwrite attempt"))
        assert [event["action"] for event in store.audit_log("store-001")] == ["ingested"]


def test_pending_update_is_explicit_and_audited(tmp_path) -> None:
    db_path = tmp_path / "review.sqlite3"
    with ReviewStore(db_path) as store:
        store.add(record())
        updated_input = NormalizedOpportunity.model_validate(
            record().model_dump(mode="python") | {"title": "Reviewed candidate title"}
        )

        updated = store.update_pending(updated_input)

        assert updated.title == "Reviewed candidate title"
        events = store.audit_log("store-001")
        assert [event["action"] for event in events] == ["ingested", "updated"]
        assert events[1]["from_state"] == ReviewState.NEEDS_REVIEW.value
        assert events[1]["to_state"] == ReviewState.NEEDS_REVIEW.value
        assert events[1]["before"]["title"] == "Stored candidate"
        assert events[1]["after"]["title"] == "Reviewed candidate title"


def test_reviewed_record_cannot_be_updated_or_transitioned_again(tmp_path) -> None:
    db_path = tmp_path / "review.sqlite3"
    with ReviewStore(db_path) as store:
        store.add(record())
        approved = store.approve("store-001")

        assert approved.review_state is ReviewState.APPROVED
        assert approved.externally_publishable is True
        with pytest.raises(ReviewStoreError, match="reviewed_record_update_forbidden"):
            store.update_pending(record(title="Attempted reviewed overwrite"))
        with pytest.raises(ReviewStoreError, match="record_already_reviewed"):
            store.reject("store-001")
        assert [event["action"] for event in store.audit_log("store-001")] == [
            "ingested",
            "approved",
        ]


def test_reject_transition_persists_across_restart(tmp_path) -> None:
    db_path = tmp_path / "review.sqlite3"
    with ReviewStore(db_path) as store:
        store.add(record("store-rejected"))
        rejected = store.reject("store-rejected")
        assert rejected.review_state is ReviewState.REJECTED
        assert rejected.externally_publishable is False

    with ReviewStore(db_path) as restarted:
        restored = restarted.get("store-rejected")
        assert restored is not None
        assert restored.review_state is ReviewState.REJECTED
        assert restored.externally_publishable is False
        assert [event["action"] for event in restarted.audit_log("store-rejected")] == [
            "ingested",
            "rejected",
        ]


def test_store_rejects_non_allowlisted_url_without_persisting_it(tmp_path) -> None:
    db_path = tmp_path / "review.sqlite3"
    unsafe = NormalizedOpportunity.model_validate(
        record().model_dump(mode="python")
        | {"source_url": "https://docs.solanamobile.com/opportunities?TOKEN_VALUE"}
    )

    with ReviewStore(db_path) as store:
        with pytest.raises(ReviewStoreError, match="record_source_not_allowed") as exc_info:
            store.add(unsafe)
        assert "TOKEN_VALUE" not in str(exc_info.value)
        assert store.list() == ()

    assert b"TOKEN_VALUE" not in db_path.read_bytes()
