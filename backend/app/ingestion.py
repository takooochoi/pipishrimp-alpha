"""Bounded, evidence-first opportunity ingestion primitives.

This module deliberately stops at a manual-review boundary.  It does not
publish records, create accounts, prepare transactions, or execute external
actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class EvidenceLabel(StrEnum):
    FACT = "Fact"
    PROJECT_CLAIM = "Project claim"
    ESTIMATE = "Estimate"
    INFERENCE = "Inference"


class ReviewState(StrEnum):
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class OpportunityStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class DeadlineState(StrEnum):
    UPCOMING = "upcoming"
    STALE = "stale"
    UNKNOWN = "unknown"
    INVALID = "invalid"
    CONFLICTING = "conflicting"


class DeadlinePrecision(StrEnum):
    DATE = "date"
    DATETIME = "datetime"
    UNKNOWN = "unknown"


class CostKind(StrEnum):
    FREE = "free"
    KNOWN = "known"
    ESTIMATE = "estimate"
    UNKNOWN = "unknown"
    INVALID = "invalid"
    CONFLICTING = "conflicting"


class SourceNotAllowed(ValueError):
    """Raised when a URL is outside the explicit official-source allowlist."""


class SourceFetchRejected(ValueError):
    """Raised when bounded fetching rejects an untrusted or unsafe response."""


class ReviewQueueError(ValueError):
    """Raised when a manual-review queue transition is invalid."""


@dataclass(frozen=True)
class OfficialSource:
    source_id: str
    publisher: str
    host: str
    path_prefix: str = "/"

    def matches(self, value: AnyHttpUrl | str) -> bool:
        raw_value = str(value)
        try:
            parsed = urlsplit(raw_value)
            port = parsed.port
            hostname = parsed.hostname
        except ValueError:
            return False
        has_query = "?" in raw_value.split("#", 1)[0]
        has_fragment = "#" in raw_value
        if (
            parsed.scheme != "https"
            or hostname != self.host
            or port not in (None, 443)
            or has_query
            or has_fragment
        ):
            return False
        if parsed.username is not None or parsed.password is not None:
            return False

        path = parsed.path or "/"
        prefix = self.path_prefix.rstrip("/") or "/"
        return prefix == "/" or path == prefix or path.startswith(f"{prefix}/")


# Keep this list intentionally small.  A source must be an official Solana
# Mobile/Seeker host and the identity is resolved from this constant, not from
# untrusted publisher text in a fetched payload.
OFFICIAL_SOURCE_ALLOWLIST: tuple[OfficialSource, ...] = (
    OfficialSource(
        source_id="solana_mobile_seeker",
        publisher="Solana Mobile / Seeker",
        host="solanamobile.com",
        path_prefix="/seeker",
    ),
    OfficialSource(
        source_id="solana_mobile",
        publisher="Solana Mobile",
        host="solanamobile.com",
    ),
    OfficialSource(
        source_id="solana_mobile_docs",
        publisher="Solana Mobile",
        host="docs.solanamobile.com",
    ),
)


class OfficialSourceAllowlist:
    def __init__(self, sources: Iterable[OfficialSource] = OFFICIAL_SOURCE_ALLOWLIST) -> None:
        self._sources = tuple(sources)

    @property
    def sources(self) -> tuple[OfficialSource, ...]:
        return self._sources

    def resolve(self, url: AnyHttpUrl | str) -> OfficialSource:
        for source in self._sources:
            if source.matches(url):
                return source
        # Never echo or chain the untrusted URL: it may contain credentials or
        # secret-bearing query/fragment data.
        raise SourceNotAllowed("source_not_allowed")


DEFAULT_ALLOWLIST = OfficialSourceAllowlist()


class NormalizedDeadline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: datetime | date | None = None
    state: DeadlineState
    precision: DeadlinePrecision
    timezone: str | None = None
    raw_value: str | None = Field(default=None, max_length=500)
    candidates: tuple[str, ...] = ()
    reason: str | None = Field(default=None, max_length=300)


class NormalizedCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal | None = None
    currency: str | None = Field(default=None, max_length=10)
    kind: CostKind
    raw_value: str | None = Field(default=None, max_length=500)
    candidates: tuple[str, ...] = ()
    reason: str | None = Field(default=None, max_length=300)


class OpportunityPayload(BaseModel):
    """Untrusted candidate payload accepted by the normalizer."""

    model_config = ConfigDict(extra="forbid")

    stable_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4_000)
    official_publisher: str = Field(min_length=1, max_length=200)
    source_id: str | None = Field(default=None, min_length=1, max_length=100)
    source_url: AnyHttpUrl
    evidence_label: EvidenceLabel
    status: OpportunityStatus = OpportunityStatus.UNKNOWN
    deadline: Any = None
    deadline_values: tuple[Any, ...] | None = None
    cost: Any = None
    cost_values: tuple[Any, ...] | None = None
    cost_currency: str | None = None
    cost_estimated: bool = False

    @model_validator(mode="after")
    def reject_ambiguous_value_inputs(self) -> OpportunityPayload:
        if self.deadline is not None and self.deadline_values is not None:
            raise ValueError("provide deadline or deadline_values, not both")
        if self.cost is not None and self.cost_values is not None:
            raise ValueError("provide cost or cost_values, not both")
        return self


class NormalizedOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    stable_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=4_000)
    official_publisher: str = Field(min_length=1, max_length=200)
    source_id: str = Field(min_length=1, max_length=100)
    source_url: AnyHttpUrl
    retrieved_at: datetime
    evidence_label: EvidenceLabel
    status: OpportunityStatus
    deadline: NormalizedDeadline
    cost: NormalizedCost
    review_state: ReviewState = ReviewState.NEEDS_REVIEW
    externally_publishable: bool = False
    review_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def enforce_publication_boundary(self) -> NormalizedOpportunity:
        if self.externally_publishable and self.review_state is not ReviewState.APPROVED:
            raise ValueError("only an approved record may be externally publishable")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")
        return self


def _utc_now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("comparison time must include a timezone")
    return current.astimezone(timezone.utc)


def _deadline_state(value: datetime | date, now: datetime) -> DeadlineState:
    if isinstance(value, datetime):
        return DeadlineState.STALE if value < now else DeadlineState.UPCOMING
    return DeadlineState.STALE if value < now.date() else DeadlineState.UPCOMING


def _invalid_deadline(raw: Any, reason: str) -> NormalizedDeadline:
    return NormalizedDeadline(
        state=DeadlineState.INVALID,
        precision=DeadlinePrecision.UNKNOWN,
        raw_value=None if raw is None else str(raw)[:500],
        reason=reason,
    )


def normalize_deadline(
    raw: Any,
    *,
    now: datetime | None = None,
    source_timezone: str | None = None,
) -> NormalizedDeadline:
    """Normalize one deadline without guessing through invalid input."""

    comparison_time = _utc_now(now)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return NormalizedDeadline(
            state=DeadlineState.UNKNOWN,
            precision=DeadlinePrecision.UNKNOWN,
            reason="deadline_missing",
        )

    if isinstance(raw, datetime):
        parsed_datetime = raw
    elif isinstance(raw, date):
        parsed_date = raw
        return NormalizedDeadline(
            value=parsed_date,
            state=_deadline_state(parsed_date, comparison_time),
            precision=DeadlinePrecision.DATE,
            timezone=None,
            raw_value=parsed_date.isoformat(),
            reason="date_only_timezone_not_applicable",
        )
    elif isinstance(raw, str):
        text = raw.strip()
        try:
            if "T" not in text and " " not in text:
                parsed_date = date.fromisoformat(text)
                return NormalizedDeadline(
                    value=parsed_date,
                    state=_deadline_state(parsed_date, comparison_time),
                    precision=DeadlinePrecision.DATE,
                    timezone=None,
                    raw_value=text,
                    reason="date_only_timezone_not_applicable",
                )
            parsed_datetime = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return _invalid_deadline(raw, "deadline_not_iso8601")
    else:
        return _invalid_deadline(raw, "deadline_type_not_supported")

    if parsed_datetime.tzinfo is None or parsed_datetime.utcoffset() is None:
        if not source_timezone:
            return _invalid_deadline(raw, "timezone_required_for_datetime")
        try:
            parsed_datetime = parsed_datetime.replace(tzinfo=ZoneInfo(source_timezone))
        except ZoneInfoNotFoundError:
            return _invalid_deadline(raw, "unknown_timezone")

    normalized = parsed_datetime.astimezone(timezone.utc)
    return NormalizedDeadline(
        value=normalized,
        state=_deadline_state(normalized, comparison_time),
        precision=DeadlinePrecision.DATETIME,
        timezone="UTC",
        raw_value=str(raw)[:500],
    )


def normalize_deadline_values(
    values: Iterable[Any],
    *,
    now: datetime | None = None,
    source_timezone: str | None = None,
) -> NormalizedDeadline:
    candidates = tuple(values)
    if not candidates:
        return normalize_deadline(None, now=now, source_timezone=source_timezone)

    normalized = [
        normalize_deadline(item, now=now, source_timezone=source_timezone) for item in candidates
    ]
    raw_candidates = tuple("" if item is None else str(item)[:500] for item in candidates)
    invalid_or_unknown = any(
        item.state in {DeadlineState.INVALID, DeadlineState.UNKNOWN} for item in normalized
    )
    known = [item for item in normalized if item.value is not None]
    keys = {(item.precision.value, str(item.value)) for item in known}
    if invalid_or_unknown and known:
        return NormalizedDeadline(
            state=DeadlineState.CONFLICTING,
            precision=DeadlinePrecision.UNKNOWN,
            raw_value=raw_candidates[0],
            candidates=raw_candidates,
            reason="known_and_invalid_or_unknown_deadlines",
        )
    if len(keys) > 1:
        return NormalizedDeadline(
            state=DeadlineState.CONFLICTING,
            precision=DeadlinePrecision.UNKNOWN,
            raw_value=raw_candidates[0],
            candidates=raw_candidates,
            reason="multiple_deadline_values",
        )
    if not known:
        return normalized[0].model_copy(update={"candidates": raw_candidates})
    return known[0].model_copy(update={"candidates": raw_candidates})


_CURRENCY_PATTERN = re.compile(r"^[A-Za-z]{2,10}$")
_FREE_VALUES = {"free", "no cost", "none", "0", "0.0", "0.00", "$0"}
_UNKNOWN_COST_VALUES = {"unknown", "tbd", "n/a", "not specified", "unspecified"}


def _normalize_currency(currency: Any) -> str | None:
    if currency is None:
        return None
    if not isinstance(currency, str) or not _CURRENCY_PATTERN.fullmatch(currency):
        return None
    return currency.upper()


def _cost_raw(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        return "structured_cost"
    return str(raw)[:500]


def _invalid_cost(raw: Any, reason: str) -> NormalizedCost:
    return NormalizedCost(kind=CostKind.INVALID, raw_value=_cost_raw(raw), reason=reason)


def normalize_cost(
    raw: Any,
    *,
    currency: str | None = None,
    estimated: bool = False,
) -> NormalizedCost:
    """Normalize cost while keeping free, unknown and estimated distinct."""

    structured_estimated = estimated
    if isinstance(raw, Mapping):
        unknown_keys = set(raw) - {"amount", "currency", "estimated"}
        if unknown_keys:
            return _invalid_cost(raw, "unsupported_cost_fields")
        if currency is not None and raw.get("currency") not in (None, currency):
            return _invalid_cost(raw, "conflicting_currency_values")
        currency = raw.get("currency", currency)
        structured_estimated_value = raw.get("estimated", estimated)
        if not isinstance(structured_estimated_value, bool):
            return _invalid_cost(raw, "estimated_must_be_boolean")
        structured_estimated = structured_estimated_value
        raw = raw.get("amount")

    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return NormalizedCost(kind=CostKind.UNKNOWN, reason="cost_missing")

    if isinstance(raw, str):
        text = raw.strip()
        lowered = text.lower()
        if lowered in _FREE_VALUES:
            normalized_currency = _normalize_currency(currency)
            if currency is not None and normalized_currency is None:
                return _invalid_cost(raw, "currency_invalid")
            return NormalizedCost(
                amount=Decimal("0"),
                currency=normalized_currency,
                kind=CostKind.FREE,
                raw_value=text,
            )
        if lowered in _UNKNOWN_COST_VALUES:
            return NormalizedCost(kind=CostKind.UNKNOWN, raw_value=text, reason="cost_unspecified")
        raw_for_decimal: Any = text
    else:
        raw_for_decimal = raw

    if isinstance(raw_for_decimal, bool):
        return _invalid_cost(raw, "boolean_is_not_a_cost")
    try:
        amount = Decimal(str(raw_for_decimal))
    except (InvalidOperation, ValueError):
        return _invalid_cost(raw, "amount_not_numeric")
    if not amount.is_finite() or amount < 0:
        return _invalid_cost(raw, "amount_must_be_finite_and_non_negative")

    normalized_currency = _normalize_currency(currency)
    if currency is not None and normalized_currency is None:
        return _invalid_cost(raw, "currency_invalid")
    if amount > 0 and normalized_currency is None:
        return _invalid_cost(raw, "currency_required_for_nonzero_cost")
    if structured_estimated:
        kind = CostKind.ESTIMATE
    elif amount == 0:
        kind = CostKind.FREE
    else:
        kind = CostKind.KNOWN
    return NormalizedCost(
        amount=amount,
        currency=normalized_currency,
        kind=kind,
        raw_value=_cost_raw(raw),
    )


def normalize_cost_values(
    values: Iterable[Any],
    *,
    currency: str | None = None,
    estimated: bool = False,
) -> NormalizedCost:
    candidates = tuple(values)
    if not candidates:
        return normalize_cost(None, currency=currency, estimated=estimated)
    normalized = [
        normalize_cost(item, currency=currency, estimated=estimated) for item in candidates
    ]
    raw_candidates = tuple(_cost_raw(item) or "" for item in candidates)
    if any(item.kind is CostKind.INVALID for item in normalized):
        if all(item.kind is CostKind.INVALID for item in normalized):
            return normalized[0].model_copy(update={"candidates": raw_candidates})
        return NormalizedCost(
            kind=CostKind.CONFLICTING,
            raw_value=raw_candidates[0],
            candidates=raw_candidates,
            reason="known_and_invalid_costs",
        )
    keys = {(item.kind.value, str(item.amount), item.currency) for item in normalized}
    if len(keys) > 1:
        return NormalizedCost(
            kind=CostKind.CONFLICTING,
            raw_value=raw_candidates[0],
            candidates=raw_candidates,
            reason="multiple_cost_values",
        )
    return normalized[0].model_copy(update={"candidates": raw_candidates})


def ingest_opportunity(
    payload: Mapping[str, Any] | OpportunityPayload,
    *,
    retrieved_at: datetime,
    now: datetime | None = None,
    allowlist: OfficialSourceAllowlist = DEFAULT_ALLOWLIST,
    source_timezone: str | None = None,
) -> NormalizedOpportunity:
    """Validate, attribute and normalize one untrusted candidate record."""

    candidate = payload if isinstance(payload, OpportunityPayload) else OpportunityPayload.model_validate(payload)
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")

    source = allowlist.resolve(candidate.source_url)
    if candidate.source_id is not None and candidate.source_id != source.source_id:
        raise SourceNotAllowed(
            f"source ID does not match allowlisted source identity: {candidate.source_id}"
        )
    if candidate.official_publisher != source.publisher:
        raise SourceNotAllowed(
            f"publisher does not match allowlisted source identity: {candidate.official_publisher}"
        )

    deadline_values = candidate.deadline_values
    if deadline_values is None:
        deadline_values = (candidate.deadline,)
    cost_values = candidate.cost_values
    if cost_values is None:
        cost_values = (candidate.cost,)

    deadline = normalize_deadline_values(
        deadline_values,
        now=now,
        source_timezone=source_timezone,
    )
    cost = normalize_cost_values(
        cost_values,
        currency=candidate.cost_currency,
        estimated=candidate.cost_estimated,
    )
    flags: list[str] = []
    if deadline.state is not DeadlineState.UPCOMING:
        flags.append(f"deadline_{deadline.state.value}")
    if cost.kind in {CostKind.UNKNOWN, CostKind.ESTIMATE, CostKind.INVALID, CostKind.CONFLICTING}:
        flags.append(f"cost_{cost.kind.value}")

    return NormalizedOpportunity(
        stable_id=candidate.stable_id,
        title=candidate.title,
        summary=candidate.summary,
        official_publisher=source.publisher,
        source_id=source.source_id,
        source_url=candidate.source_url,
        retrieved_at=retrieved_at,
        evidence_label=candidate.evidence_label,
        status=candidate.status,
        deadline=deadline,
        cost=cost,
        review_flags=tuple(flags),
    )


class ReviewQueue:
    """In-memory manual-review boundary; no external publication is performed."""

    def __init__(self) -> None:
        self._records: dict[str, NormalizedOpportunity] = {}

    def submit(self, record: NormalizedOpportunity) -> NormalizedOpportunity:
        if record.stable_id in self._records:
            raise ReviewQueueError(f"record already exists: {record.stable_id}")
        pending = NormalizedOpportunity.model_validate(
            record.model_dump(mode="python")
            | {
                "review_state": ReviewState.NEEDS_REVIEW,
                "externally_publishable": False,
            }
        )
        self._records[pending.stable_id] = pending
        return pending

    def get(self, stable_id: str) -> NormalizedOpportunity | None:
        return self._records.get(stable_id)

    def list(self, *, state: ReviewState | None = None) -> tuple[NormalizedOpportunity, ...]:
        records = tuple(self._records.values())
        if state is not None:
            records = tuple(record for record in records if record.review_state is state)
        return tuple(sorted(records, key=lambda record: record.stable_id))

    def approve(self, stable_id: str) -> NormalizedOpportunity:
        return self._transition(stable_id, ReviewState.APPROVED, True)

    def reject(self, stable_id: str) -> NormalizedOpportunity:
        return self._transition(stable_id, ReviewState.REJECTED, False)

    def _transition(
        self,
        stable_id: str,
        state: ReviewState,
        externally_publishable: bool,
    ) -> NormalizedOpportunity:
        current = self._records.get(stable_id)
        if current is None:
            raise ReviewQueueError(f"record not found: {stable_id}")
        updated = NormalizedOpportunity.model_validate(
            current.model_dump(mode="python")
            | {
                "review_state": state,
                "externally_publishable": externally_publishable,
            }
        )
        self._records[stable_id] = updated
        return updated


@dataclass(frozen=True)
class FetchPolicy:
    timeout_seconds: float = 5.0
    max_bytes: int = 256_000
    max_redirects: int = 3
    accepted_content_types: tuple[str, ...] = (
        "application/json",
        "application/xhtml+xml",
        "text/html",
    )

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")


@dataclass(frozen=True)
class FetchedSource:
    source_id: str
    publisher: str
    url: str
    retrieved_at: datetime
    content_type: str
    body: bytes


class _NoAutomaticRedirectHandler(HTTPRedirectHandler):
    """Return redirect responses so the fetcher can validate before following."""

    @staticmethod
    def _return_response(
        request: Request,
        response: Any,
        code: int,
        message: str,
        headers: Any,
    ) -> Any:
        return response

    def http_error_301(self, request: Request, response: Any, code: int, message: str, headers: Any) -> Any:
        return self._return_response(request, response, code, message, headers)

    def http_error_302(self, request: Request, response: Any, code: int, message: str, headers: Any) -> Any:
        return self._return_response(request, response, code, message, headers)

    def http_error_303(self, request: Request, response: Any, code: int, message: str, headers: Any) -> Any:
        return self._return_response(request, response, code, message, headers)

    def http_error_307(self, request: Request, response: Any, code: int, message: str, headers: Any) -> Any:
        return self._return_response(request, response, code, message, headers)

    def http_error_308(self, request: Request, response: Any, code: int, message: str, headers: Any) -> Any:
        return self._return_response(request, response, code, message, headers)


class BoundedOfficialSourceFetcher:
    """Read-only bounded HTTP fetcher for allowlisted official sources."""

    def __init__(
        self,
        *,
        allowlist: OfficialSourceAllowlist = DEFAULT_ALLOWLIST,
        policy: FetchPolicy = FetchPolicy(),
        opener: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._allowlist = allowlist
        self._policy = policy
        self._opener = opener or build_opener(_NoAutomaticRedirectHandler()).open
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch(self, url: AnyHttpUrl | str) -> FetchedSource:
        current_url = str(url)
        source = self._allowlist.resolve(current_url)
        redirect_count = 0

        while True:
            request = Request(
                current_url,
                headers={
                    "Accept": ", ".join(self._policy.accepted_content_types),
                    "User-Agent": "BCOP-official-opportunity-ingestor/1.0",
                },
                method="GET",
            )
            try:
                with self._opener(request, timeout=self._policy.timeout_seconds) as response:
                    status = getattr(response, "status", None) or response.getcode()
                    headers = getattr(response, "headers", None)
                    if status is not None and 300 <= status < 400:
                        location = headers.get("Location", "") if headers else ""
                        if not location:
                            raise SourceFetchRejected("redirect response has no Location")
                        if redirect_count >= self._policy.max_redirects:
                            raise SourceFetchRejected("redirect limit exceeded")
                        target_url = urljoin(current_url, location)
                        try:
                            target_source = self._allowlist.resolve(target_url)
                        except SourceNotAllowed:
                            raise SourceFetchRejected("redirect_target_not_allowed") from None
                        if target_source.source_id != source.source_id:
                            raise SourceFetchRejected(
                                "redirect target changes the original source identity"
                            )
                        current_url = target_url
                        redirect_count += 1
                        continue
                    if status is not None and status >= 400:
                        raise SourceFetchRejected(f"source returned HTTP {status}")
                    content_type_header = headers.get("Content-Type", "") if headers else ""
                    content_type = content_type_header.split(";", 1)[0].strip().lower()
                    if content_type not in self._policy.accepted_content_types:
                        raise SourceFetchRejected(
                            f"content type is not allowed: {content_type or 'missing'}"
                        )
                    content_length = headers.get("Content-Length") if headers else None
                    if content_length is not None:
                        try:
                            parsed_length = int(content_length)
                        except ValueError:
                            raise SourceFetchRejected("invalid content length") from None
                        if parsed_length < 0 or parsed_length > self._policy.max_bytes:
                            raise SourceFetchRejected("content length exceeds bounded limit")
                    body = response.read(self._policy.max_bytes + 1)
                    if len(body) > self._policy.max_bytes:
                        raise SourceFetchRejected("response exceeds bounded byte limit")
                    final_url = current_url
                    break
            except SourceFetchRejected:
                raise
            except (HTTPError, URLError, TimeoutError, OSError):
                raise SourceFetchRejected("bounded source fetch failed") from None

        final_source = self._allowlist.resolve(final_url)
        if final_source.source_id != source.source_id:
            raise SourceFetchRejected("redirected outside the original allowlisted source")
        retrieved_at = self._clock()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise SourceFetchRejected("fetch clock must include a timezone")
        return FetchedSource(
            source_id=final_source.source_id,
            publisher=final_source.publisher,
            url=final_url,
            retrieved_at=retrieved_at,
            content_type=content_type,
            body=body,
        )


def ingest_fetched_opportunity(
    fetched: FetchedSource,
    payload: Mapping[str, Any] | OpportunityPayload,
    *,
    now: datetime | None = None,
    allowlist: OfficialSourceAllowlist = DEFAULT_ALLOWLIST,
    source_timezone: str | None = None,
) -> NormalizedOpportunity:
    """Attach verified fetch provenance before normalizing an untrusted record."""

    fetched_source = allowlist.resolve(fetched.url)
    if (
        fetched.source_id != fetched_source.source_id
        or fetched.publisher != fetched_source.publisher
    ):
        raise SourceNotAllowed("fetched source metadata does not match the allowlist")

    candidate = (
        payload.model_dump(mode="python")
        if isinstance(payload, OpportunityPayload)
        else dict(payload)
    )
    if "source_url" in candidate and (
        candidate["source_url"] is None or str(candidate["source_url"]) != fetched.url
    ):
        raise SourceNotAllowed("payload source URL does not match fetched provenance")
    if "official_publisher" in candidate and candidate["official_publisher"] != fetched.publisher:
        raise SourceNotAllowed("payload publisher does not match fetched provenance")
    if "source_id" in candidate and candidate["source_id"] != fetched.source_id:
        raise SourceNotAllowed("payload source ID does not match fetched provenance")
    candidate["source_url"] = fetched.url
    candidate["official_publisher"] = fetched.publisher
    candidate["source_id"] = fetched.source_id
    return ingest_opportunity(
        candidate,
        retrieved_at=fetched.retrieved_at,
        now=now,
        allowlist=allowlist,
        source_timezone=source_timezone,
    )
