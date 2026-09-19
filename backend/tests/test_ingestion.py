from datetime import date, datetime, timezone
from decimal import Decimal
from traceback import format_exception

import pytest
from pydantic import ValidationError

from app.ingestion import (
    BoundedOfficialSourceFetcher,
    CostKind,
    DeadlineState,
    EvidenceLabel,
    FetchPolicy,
    FetchedSource,
    OpportunityStatus,
    ReviewQueue,
    ReviewQueueError,
    ReviewState,
    SourceFetchRejected,
    SourceNotAllowed,
    ingest_fetched_opportunity,
    normalize_cost,
    normalize_cost_values,
    normalize_deadline,
    normalize_deadline_values,
    ingest_opportunity,
)


NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
RETRIEVED_AT = datetime(2026, 9, 18, 12, 5, tzinfo=timezone.utc)


def payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "stable_id": "seeker-001",
        "title": "Official Seeker opportunity",
        "summary": "Review the official opportunity terms before any human decision.",
        "official_publisher": "Solana Mobile / Seeker",
        "source_url": "https://solanamobile.com/seeker/opportunities",
        "evidence_label": "Fact",
        "status": "open",
        "deadline": "2026-09-20",
        "cost": {"amount": "0", "currency": "USD"},
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize("label", ["Fact", "Project claim", "Estimate", "Inference"])
def test_all_evidence_labels_are_preserved(label: str) -> None:
    record = ingest_opportunity(
        payload(evidence_label=label),
        retrieved_at=RETRIEVED_AT,
        now=NOW,
    )

    assert record.evidence_label.value == label
    assert record.review_state is ReviewState.NEEDS_REVIEW
    assert record.externally_publishable is False


def test_missing_evidence_label_is_rejected() -> None:
    candidate = payload()
    del candidate["evidence_label"]

    with pytest.raises(ValidationError):
        ingest_opportunity(candidate, retrieved_at=RETRIEVED_AT, now=NOW)


def test_project_claim_is_not_promoted_to_fact() -> None:
    record = ingest_opportunity(
        payload(evidence_label="Project claim"),
        retrieved_at=RETRIEVED_AT,
        now=NOW,
    )

    assert record.evidence_label is EvidenceLabel.PROJECT_CLAIM
    assert record.evidence_label is not EvidenceLabel.FACT


def test_non_allowlisted_or_mismatched_source_is_rejected() -> None:
    with pytest.raises(SourceNotAllowed):
        ingest_opportunity(
            payload(source_url="https://example.com/opportunity"),
            retrieved_at=RETRIEVED_AT,
            now=NOW,
        )
    with pytest.raises(SourceNotAllowed):
        ingest_opportunity(
            payload(official_publisher="Untrusted publisher"),
            retrieved_at=RETRIEVED_AT,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("source_url", "secret"),
    [
        ("https://user:pass@docs.solanamobile.com/opportunities", "user:pass"),
        ("https://docs.solanamobile.com/opportunities?token=SECRET", "SECRET"),
        ("https://docs.solanamobile.com/opportunities#SECRET", "SECRET"),
    ],
)
def test_initial_source_url_policy_rejects_secrets_without_echoing_them(
    source_url: str,
    secret: str,
) -> None:
    with pytest.raises(SourceNotAllowed) as exc_info:
        ingest_opportunity(
            payload(source_url=source_url),
            retrieved_at=RETRIEVED_AT,
            now=NOW,
        )

    assert str(exc_info.value) == "source_not_allowed"
    assert secret not in "".join(format_exception(exc_info.value))


def test_deadline_normalization_handles_timezone_unknown_invalid_stale_and_conflict() -> None:
    date_only = normalize_deadline("2026-09-20", now=NOW)
    assert date_only.value == date(2026, 9, 20)
    assert date_only.state is DeadlineState.UPCOMING
    assert date_only.timezone is None

    aware = normalize_deadline("2026-09-20T10:00:00+10:00", now=NOW)
    assert aware.value == datetime(2026, 9, 20, tzinfo=timezone.utc)
    assert aware.timezone == "UTC"

    naive = normalize_deadline("2026-09-20T10:00:00", now=NOW)
    assert naive.state is DeadlineState.INVALID
    assert naive.reason == "timezone_required_for_datetime"

    stale = normalize_deadline("2026-09-17", now=NOW)
    assert stale.state is DeadlineState.STALE

    unknown = normalize_deadline(None, now=NOW)
    assert unknown.state is DeadlineState.UNKNOWN

    conflict = normalize_deadline_values(["2026-09-20", "2026-09-21"], now=NOW)
    assert conflict.state is DeadlineState.CONFLICTING
    assert len(conflict.candidates) == 2


def test_cost_normalization_keeps_free_unknown_estimate_and_invalid_distinct() -> None:
    assert normalize_cost("free").kind is CostKind.FREE
    assert normalize_cost("free", currency="not-a-currency").kind is CostKind.INVALID
    assert normalize_cost("25", currency="USD").model_dump()["amount"] == Decimal("25")
    assert normalize_cost({"amount": "25", "currency": "USDC", "estimated": True}).kind is CostKind.ESTIMATE
    assert normalize_cost({"amount": "25", "currency": "USDC", "estimated": "yes"}).kind is CostKind.INVALID
    assert normalize_cost(None).kind is CostKind.UNKNOWN
    assert normalize_cost("25").kind is CostKind.INVALID
    assert normalize_cost("future reward claim", currency="USD").kind is CostKind.INVALID

    conflict = normalize_cost_values(
        [{"amount": "10", "currency": "USD"}, {"amount": "20", "currency": "USD"}]
    )
    assert conflict.kind is CostKind.CONFLICTING


def test_invalid_deadline_and_cost_are_surfaced_on_pending_record() -> None:
    record = ingest_opportunity(
        payload(
            deadline="2026-09-20T10:00:00",
            cost="25",
        ),
        retrieved_at=RETRIEVED_AT,
        now=NOW,
    )

    assert record.deadline.state is DeadlineState.INVALID
    assert record.cost.kind is CostKind.INVALID
    assert "deadline_invalid" in record.review_flags
    assert "cost_invalid" in record.review_flags
    assert record.review_state is ReviewState.NEEDS_REVIEW
    assert record.externally_publishable is False


def test_review_queue_requires_explicit_manual_transition() -> None:
    record = ingest_opportunity(payload(), retrieved_at=RETRIEVED_AT, now=NOW)
    queue = ReviewQueue()

    pending = queue.submit(record)
    assert pending.review_state is ReviewState.NEEDS_REVIEW
    assert queue.list(state=ReviewState.NEEDS_REVIEW) == (pending,)

    approved = queue.approve(record.stable_id)
    assert approved.review_state is ReviewState.APPROVED
    assert approved.externally_publishable is True

    rejected_queue = ReviewQueue()
    rejected_queue.submit(record)
    rejected = rejected_queue.reject(record.stable_id)
    assert rejected.review_state is ReviewState.REJECTED
    assert rejected.externally_publishable is False

    with pytest.raises(ReviewQueueError):
        queue.submit(record)


def test_publication_boundary_rejects_unreviewed_publish_flag() -> None:
    record = ingest_opportunity(payload(), retrieved_at=RETRIEVED_AT, now=NOW)

    with pytest.raises(ValidationError):
        record.model_copy(update={"externally_publishable": True}).model_validate(
            record.model_dump(mode="python") | {"externally_publishable": True}
        )


class FakeHeaders(dict[str, str]):
    pass


class FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status: int = 200,
        location: str | None = None,
        content_type: str = "text/html",
        body: bytes = b"<html />",
    ) -> None:
        self._url = url
        self.status = status
        self.headers = FakeHeaders({"Content-Type": content_type, "Content-Length": str(len(body))})
        if location is not None:
            self.headers["Location"] = location
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        return self._body[:size]


def test_bounded_fetcher_accepts_allowlisted_content_and_records_retrieval() -> None:
    fetcher = BoundedOfficialSourceFetcher(
        opener=lambda request, timeout: FakeResponse(url=request.full_url),
        clock=lambda: RETRIEVED_AT,
    )

    fetched = fetcher.fetch("https://docs.solanamobile.com/opportunities")

    assert fetched.source_id == "solana_mobile_docs"
    assert fetched.publisher == "Solana Mobile"
    assert fetched.retrieved_at == RETRIEVED_AT
    assert fetched.body == b"<html />"


def test_bounded_fetcher_allows_same_source_redirect_before_next_request() -> None:
    calls: list[str] = []
    responses = [
        FakeResponse(
            url="https://docs.solanamobile.com/opportunities",
            status=302,
            location="/opportunities/current",
            body=b"",
        ),
        FakeResponse(url="https://docs.solanamobile.com/opportunities/current"),
    ]

    def opener(request: object, timeout: float) -> FakeResponse:
        calls.append(request.full_url)
        return responses.pop(0)

    fetched = BoundedOfficialSourceFetcher(opener=opener).fetch(
        "https://docs.solanamobile.com/opportunities"
    )

    assert calls == [
        "https://docs.solanamobile.com/opportunities",
        "https://docs.solanamobile.com/opportunities/current",
    ]
    assert fetched.url == "https://docs.solanamobile.com/opportunities/current"


@pytest.mark.parametrize(
    "location",
    [
        "https://example.com/redirected",
        "http://127.0.0.1:8011/healthz",
        "https://solanamobile.com/seeker/opportunities",
    ],
)
def test_bounded_fetcher_rejects_disallowed_redirect_before_second_request(
    location: str,
) -> None:
    calls: list[str] = []

    def opener(request: object, timeout: float) -> FakeResponse:
        calls.append(request.full_url)
        return FakeResponse(
            url=request.full_url,
            status=302,
            location=location,
            body=b"",
        )

    with pytest.raises(SourceFetchRejected):
        BoundedOfficialSourceFetcher(opener=opener).fetch(
            "https://docs.solanamobile.com/opportunities"
        )
    assert calls == ["https://docs.solanamobile.com/opportunities"]


def test_bounded_fetcher_rejects_redirect_query_secret_before_next_request() -> None:
    calls: list[str] = []

    def opener(request: object, timeout: float) -> FakeResponse:
        calls.append(request.full_url)
        return FakeResponse(
            url=request.full_url,
            status=302,
            location="/opportunities/current?token=SECRET",
            body=b"",
        )

    with pytest.raises(SourceFetchRejected) as exc_info:
        BoundedOfficialSourceFetcher(opener=opener).fetch(
            "https://docs.solanamobile.com/opportunities"
        )

    assert calls == ["https://docs.solanamobile.com/opportunities"]
    assert str(exc_info.value) == "redirect_target_not_allowed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    assert "SECRET" not in "".join(format_exception(exc_info.value))


def test_bounded_fetcher_rejects_redirect_chain_that_tries_to_bypass_policy() -> None:
    calls: list[str] = []
    responses = [
        FakeResponse(
            url="https://docs.solanamobile.com/opportunities",
            status=302,
            location="/opportunities/step-1",
            body=b"",
        ),
        FakeResponse(
            url="https://docs.solanamobile.com/opportunities/step-1",
            status=302,
            location="http://127.0.0.1/",
            body=b"",
        ),
    ]

    def opener(request: object, timeout: float) -> FakeResponse:
        calls.append(request.full_url)
        return responses.pop(0)

    with pytest.raises(SourceFetchRejected):
        BoundedOfficialSourceFetcher(opener=opener).fetch(
            "https://docs.solanamobile.com/opportunities"
        )
    assert calls == [
        "https://docs.solanamobile.com/opportunities",
        "https://docs.solanamobile.com/opportunities/step-1",
    ]


def test_bounded_fetcher_rejects_oversize_response() -> None:
    oversized = BoundedOfficialSourceFetcher(
        policy=FetchPolicy(max_bytes=4),
        opener=lambda request, timeout: FakeResponse(url=request.full_url, body=b"12345"),
    )
    with pytest.raises(SourceFetchRejected):
        oversized.fetch("https://docs.solanamobile.com/opportunities")


def test_bounded_fetcher_rejects_non_allowlisted_url_before_network() -> None:
    called = False

    def opener(request: object, timeout: float) -> FakeResponse:
        nonlocal called
        called = True
        return FakeResponse(url="https://example.com")

    fetcher = BoundedOfficialSourceFetcher(opener=opener)
    with pytest.raises(SourceNotAllowed):
        fetcher.fetch("https://example.com/opportunity")
    assert called is False


def test_fetched_source_provenance_feeds_normalization_and_review() -> None:
    fetched = FetchedSource(
        source_id="solana_mobile_docs",
        publisher="Solana Mobile",
        url="https://docs.solanamobile.com/opportunities",
        retrieved_at=RETRIEVED_AT,
        content_type="text/html",
        body=b"<html />",
    )

    record = ingest_fetched_opportunity(
        fetched,
        {
            "stable_id": "seeker-001",
            "title": "Seeker opportunity",
            "summary": "Candidate imported from the official source.",
            "evidence_label": "Project claim",
            "deadline": "2099-01-01",
            "cost": "free",
        },
        now=NOW,
    )

    assert record.source_id == "solana_mobile_docs"
    assert record.retrieved_at == RETRIEVED_AT
    assert record.review_state is ReviewState.NEEDS_REVIEW
    assert record.externally_publishable is False


def test_fetched_source_provenance_rejects_mismatched_payload_fields() -> None:
    fetched = FetchedSource(
        source_id="solana_mobile_docs",
        publisher="Solana Mobile",
        url="https://docs.solanamobile.com/opportunities",
        retrieved_at=RETRIEVED_AT,
        content_type="text/html",
        body=b"<html />",
    )

    with pytest.raises(SourceNotAllowed):
        ingest_fetched_opportunity(
            fetched,
            {
                "stable_id": "seeker-url-mismatch",
                "title": "Mismatch",
                "summary": "The payload attempts to change its source.",
                "source_url": "https://solanamobile.com/seeker/opportunities",
                "official_publisher": "Solana Mobile",
                "evidence_label": "Fact",
            },
        )
    with pytest.raises(SourceNotAllowed):
        ingest_fetched_opportunity(
            fetched,
            {
                "stable_id": "seeker-publisher-mismatch",
                "title": "Mismatch",
                "summary": "The payload attempts to change its publisher.",
                "source_url": fetched.url,
                "official_publisher": "Solana Mobile / Seeker",
                "evidence_label": "Fact",
            },
        )
    with pytest.raises(SourceNotAllowed):
        ingest_fetched_opportunity(
            fetched,
            {
                "stable_id": "seeker-id-mismatch",
                "title": "Mismatch",
                "summary": "The payload attempts to change its source ID.",
                "source_url": fetched.url,
                "official_publisher": fetched.publisher,
                "source_id": "solana_mobile",
                "evidence_label": "Fact",
            },
        )


def test_fetched_source_provenance_accepts_exact_matching_fields() -> None:
    fetched = FetchedSource(
        source_id="solana_mobile_docs",
        publisher="Solana Mobile",
        url="https://docs.solanamobile.com/opportunities",
        retrieved_at=RETRIEVED_AT,
        content_type="text/html",
        body=b"<html />",
    )

    record = ingest_fetched_opportunity(
        fetched,
        {
            "stable_id": "seeker-matching-provenance",
            "title": "Matching provenance",
            "summary": "Payload fields exactly match the verified fetch provenance.",
            "source_url": fetched.url,
            "official_publisher": fetched.publisher,
            "source_id": fetched.source_id,
            "evidence_label": "Fact",
        },
    )

    assert record.source_id == fetched.source_id
    assert str(record.source_url) == fetched.url
