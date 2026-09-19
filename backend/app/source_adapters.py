"""Bounded adapters for the two initial official Solana Mobile articles.

These adapters intentionally parse only a small, deterministic HTML contract
from content already returned by ``BoundedOfficialSourceFetcher``. They do not
execute scripts, follow links, or attempt to discover other sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
import re
from typing import Iterable

from .ingestion import (
    EvidenceLabel,
    FetchPolicy,
    FetchedSource,
    NormalizedOpportunity,
    OpportunityStatus,
    ingest_fetched_opportunity,
)


class SourceAdapterError(ValueError):
    """Raised when a configured source does not match its bounded contract."""


INITIAL_SOURCE_FETCH_POLICY = FetchPolicy(max_bytes=512_000)


@dataclass(frozen=True)
class _ArticleFields:
    title: str
    paragraphs: tuple[str, ...]


class _VisibleArticleParser(HTMLParser):
    """Collect only h1/p text; scripts and styles are never interpreted."""

    _ignored_tags = frozenset({"script", "style", "noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[str] = []
        self.paragraphs: list[str] = []
        self._ignored_depth = 0
        self._capture_tag: str | None = None
        self._capture_depth = 0
        self._capture_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if self._ignored_depth:
            if tag in self._ignored_tags:
                self._ignored_depth += 1
            return
        if tag in self._ignored_tags:
            self._ignored_depth = 1
            return
        if self._capture_tag is not None:
            self._capture_depth += 1
            return
        if tag in {"h1", "p"}:
            self._capture_tag = tag
            self._capture_depth = 1
            self._capture_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._ignored_depth:
            if tag in self._ignored_tags:
                self._ignored_depth -= 1
            return
        if self._capture_tag is None:
            return
        if self._capture_depth > 1:
            self._capture_depth -= 1
            return
        if tag != self._capture_tag:
            return
        text = " ".join("".join(self._capture_parts).split())
        if text:
            if self._capture_tag == "h1":
                self.headings.append(text)
            else:
                self.paragraphs.append(text)
        self._capture_tag = None
        self._capture_depth = 0
        self._capture_parts = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0 and self._capture_tag is not None:
            self._capture_parts.append(data)


_DATE_PATTERN = re.compile(
    r"\b(?:"
    r"\d{4}-\d{2}-\d{2}"
    r"|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r")\b",
    re.IGNORECASE,
)
_DEADLINE_MARKER = re.compile(
    r"\b(?:deadline|submissions?\s+(?:close|due)|applications?\s+(?:close|due)|"
    r"apply\s+by|submit\s+by)\b",
    re.IGNORECASE,
)


def _parse_article(body: bytes) -> _ArticleFields:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SourceAdapterError("source_body_not_utf8") from None

    parser = _VisibleArticleParser()
    try:
        parser.feed(text)
        parser.close()
    except (RuntimeError, ValueError):
        raise SourceAdapterError("source_structure_invalid") from None

    if len(parser.headings) != 1 or not parser.paragraphs:
        raise SourceAdapterError("source_structure_invalid")
    return _ArticleFields(title=parser.headings[0], paragraphs=tuple(parser.paragraphs))


def _summary(paragraphs: Iterable[str]) -> str:
    for paragraph in paragraphs:
        if len(paragraph) >= 40:
            return paragraph
    raise SourceAdapterError("source_summary_missing")


def _deadline_values(paragraphs: Iterable[str]) -> tuple[str, ...]:
    values: list[str] = []
    for paragraph in paragraphs:
        if not _DEADLINE_MARKER.search(paragraph):
            continue
        for match in _DATE_PATTERN.finditer(paragraph):
            raw = match.group(0).replace(",", "")
            raw = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)
            try:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                    parsed = date.fromisoformat(raw)
                else:
                    parsed = datetime.strptime(raw, "%B %d %Y").date()
            except ValueError:
                continue
            iso_value = parsed.isoformat()
            if iso_value not in values:
                values.append(iso_value)
    return tuple(values)


def _validate_fetch(
    fetched: FetchedSource,
    *,
    source_url: str,
    source_id: str,
    publisher: str,
) -> None:
    if (
        fetched.url != source_url
        or fetched.source_id != source_id
        or fetched.publisher != publisher
        or fetched.content_type not in {"text/html", "application/xhtml+xml"}
    ):
        raise SourceAdapterError("source_provenance_or_content_type_invalid")


def _normalize_article(
    fetched: FetchedSource,
    *,
    stable_id: str,
    expected_title: str,
    source_url: str,
    source_id: str,
    publisher: str,
    now: datetime | None,
) -> NormalizedOpportunity:
    _validate_fetch(
        fetched,
        source_url=source_url,
        source_id=source_id,
        publisher=publisher,
    )
    fields = _parse_article(fetched.body)
    if fields.title != expected_title:
        raise SourceAdapterError("source_title_mismatch")

    deadline_values = _deadline_values(fields.paragraphs)
    payload: dict[str, object] = {
        "stable_id": stable_id,
        "title": fields.title,
        "summary": _summary(fields.paragraphs),
        "official_publisher": publisher,
        "source_id": source_id,
        "source_url": fetched.url,
        "evidence_label": EvidenceLabel.PROJECT_CLAIM,
        "status": OpportunityStatus.UNKNOWN,
        "deadline_values": deadline_values or None,
        # Reward/prize/grant amounts are source claims, not participation cost.
        "cost": None,
    }
    record = ingest_fetched_opportunity(fetched, payload, now=now)
    flags = list(record.review_flags)
    flags.append("status_unknown")
    return NormalizedOpportunity.model_validate(
        record.model_dump(mode="python") | {"review_flags": tuple(dict.fromkeys(flags))}
    )


@dataclass(frozen=True)
class ClockInSourceAdapter:
    """Adapter for the official CLOCK IN hackathon article."""

    name: str = "clock-in"
    source_id: str = "solana_mobile"
    publisher: str = "Solana Mobile"
    source_url: str = "https://solanamobile.com/blog/clock-in-the-solana-mobile-hackathon"
    stable_id: str = "solana-mobile-clock-in-hackathon"
    expected_title: str = "CLOCK IN: The Solana Mobile Hackathon"

    def parse(
        self,
        fetched: FetchedSource,
        *,
        now: datetime | None = None,
    ) -> NormalizedOpportunity:
        return _normalize_article(
            fetched,
            stable_id=self.stable_id,
            expected_title=self.expected_title,
            source_url=self.source_url,
            source_id=self.source_id,
            publisher=self.publisher,
            now=now,
        )


@dataclass(frozen=True)
class BuilderGrantsSourceAdapter:
    """Adapter for the official Solana Mobile Builder Grants article."""

    name: str = "builder-grants"
    source_id: str = "solana_mobile"
    publisher: str = "Solana Mobile"
    source_url: str = (
        "https://solanamobile.com/blog/solana-mobile-builder-grants-bring-your-best-seeker-and-skr-ideas"
    )
    stable_id: str = "solana-mobile-builder-grants"
    expected_title: str = "Solana Mobile Builder Grants: Bring Your Best Seeker and SKR Ideas"

    def parse(
        self,
        fetched: FetchedSource,
        *,
        now: datetime | None = None,
    ) -> NormalizedOpportunity:
        return _normalize_article(
            fetched,
            stable_id=self.stable_id,
            expected_title=self.expected_title,
            source_url=self.source_url,
            source_id=self.source_id,
            publisher=self.publisher,
            now=now,
        )


INITIAL_SOURCE_ADAPTERS: tuple[ClockInSourceAdapter | BuilderGrantsSourceAdapter, ...] = (
    ClockInSourceAdapter(),
    BuilderGrantsSourceAdapter(),
)


def adapter_by_name(name: str) -> ClockInSourceAdapter | BuilderGrantsSourceAdapter:
    for adapter in INITIAL_SOURCE_ADAPTERS:
        if name in {adapter.name, adapter.stable_id, adapter.source_url}:
            return adapter
    raise SourceAdapterError("source_adapter_not_configured")
