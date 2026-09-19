from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.ingestion import FetchedSource, ReviewState
from app.source_adapters import (
    BuilderGrantsSourceAdapter,
    ClockInSourceAdapter,
    SourceAdapterError,
)


FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
RETRIEVED_AT = datetime(2026, 9, 18, 12, 5, tzinfo=timezone.utc)


def fetched(adapter: object, fixture_name: str) -> FetchedSource:
    return FetchedSource(
        source_id=adapter.source_id,
        publisher=adapter.publisher,
        url=adapter.source_url,
        retrieved_at=RETRIEVED_AT,
        content_type="text/html",
        body=(FIXTURES / fixture_name).read_bytes(),
    )


def test_clock_in_adapter_extracts_normalized_candidate_from_fixture() -> None:
    adapter = ClockInSourceAdapter()

    record = adapter.parse(fetched(adapter, "clock_in.html"), now=NOW)

    assert record.stable_id == "solana-mobile-clock-in-hackathon"
    assert record.title == "CLOCK IN: The Solana Mobile Hackathon"
    assert record.summary.startswith("The CLOCK IN hackathon invites builders")
    assert str(record.source_url) == adapter.source_url
    assert record.source_id == adapter.source_id
    assert record.official_publisher == adapter.publisher
    assert "Untrusted script content" not in record.summary
    assert record.evidence_label.value == "Project claim"
    assert record.deadline.value == date(2026, 10, 1)
    assert record.cost.kind.value == "unknown"
    assert "cost_unknown" in record.review_flags
    assert "status_unknown" in record.review_flags
    assert record.review_state is ReviewState.NEEDS_REVIEW
    assert record.externally_publishable is False


def test_builder_grants_adapter_preserves_unknown_fields_for_review() -> None:
    adapter = BuilderGrantsSourceAdapter()

    record = adapter.parse(fetched(adapter, "builder_grants.html"), now=NOW)

    assert record.stable_id == "solana-mobile-builder-grants"
    assert record.title == "Solana Mobile Builder Grants: Bring Your Best Seeker and SKR Ideas"
    assert record.deadline.value is None
    assert record.deadline.state.value == "unknown"
    assert record.cost.amount is None
    assert record.cost.kind.value == "unknown"
    assert record.evidence_label.value == "Project claim"
    assert record.review_state is ReviewState.NEEDS_REVIEW
    assert record.externally_publishable is False


@pytest.mark.parametrize("field", ["url", "source_id", "publisher", "content_type"])
def test_adapters_fail_closed_on_provenance_or_content_mismatch(field: str) -> None:
    adapter = ClockInSourceAdapter()
    source = fetched(adapter, "clock_in.html")
    replacement = {
        "url": "https://solanamobile.com/blog/other",
        "source_id": "wrong_source",
        "publisher": "Untrusted publisher",
        "content_type": "application/json",
    }[field]
    invalid = FetchedSource(
        source_id=replacement if field == "source_id" else source.source_id,
        publisher=replacement if field == "publisher" else source.publisher,
        url=replacement if field == "url" else source.url,
        retrieved_at=source.retrieved_at,
        content_type=replacement if field == "content_type" else source.content_type,
        body=source.body,
    )

    with pytest.raises(SourceAdapterError, match="source_provenance_or_content_type_invalid"):
        adapter.parse(invalid, now=NOW)


def test_adapter_surfaces_conflicting_deadlines_without_guessing() -> None:
    adapter = ClockInSourceAdapter()
    body = (
        b"<article><h1>CLOCK IN: The Solana Mobile Hackathon</h1>"
        b"<p>Build with the official mobile ecosystem.</p>"
        b"<p>Submission deadline: 2026-10-01.</p>"
        b"<p>Applications close: October 5, 2026.</p></article>"
    )
    source = fetched(adapter, "clock_in.html")
    conflicting = FetchedSource(
        source_id=source.source_id,
        publisher=source.publisher,
        url=source.url,
        retrieved_at=source.retrieved_at,
        content_type=source.content_type,
        body=body,
    )

    record = adapter.parse(conflicting, now=NOW)

    assert record.deadline.state.value == "conflicting"
    assert "deadline_conflicting" in record.review_flags
