from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Protocol

from app.models import Opportunity, RiskLevel
from app.scoring import ScoreComponents, calculate_bcop_score


class OpportunityRepository(Protocol):
    def list(self, *, category: str | None = None, risk_level: RiskLevel | None = None) -> list[Opportunity]: ...

    def get(self, opportunity_id: str) -> Opportunity | None: ...


def _sample(
    *,
    opportunity_id: str,
    title: str,
    category: str,
    source_url: str,
    source_type: str,
    capital_required_usd: float,
    estimated_human_minutes: int,
    reward_type: str,
    reward_certainty: str,
    deadline: date | None,
    risk_level: RiskLevel,
    components: ScoreComponents,
    recommended_action: str,
    summary: str,
) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        project_id=None,
        title=title,
        category=category,
        source_url=source_url,
        source_type=source_type,
        evidence_level="sample",
        capital_required_usd=capital_required_usd,
        estimated_human_minutes=estimated_human_minutes,
        reward_type=reward_type,
        reward_certainty=reward_certainty,
        deadline=deadline,
        risk_level=risk_level,
        score_components=components,
        bcop_score=calculate_bcop_score(components),
        recommended_action=recommended_action,
        fetched_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        is_sample=True,
        summary=summary,
    )


SAMPLE_OPPORTUNITIES = [
    _sample(
        opportunity_id="sample-mobile-docs",
        title="Sample: review official Solana Mobile developer updates",
        category="research",
        source_url="https://docs.solanamobile.com/",
        source_type="official_docs_example",
        capital_required_usd=0,
        estimated_human_minutes=30,
        reward_type="No reward — demo only",
        reward_certainty="sample_only",
        deadline=None,
        risk_level=RiskLevel.LOW,
        components=ScoreComponents(
            expected_roi=17,
            evidence_quality=17,
            capital_efficiency=15,
            ai_leverage=10,
            strategic_value=14,
            risk=9,
        ),
        recommended_action="Open the official source and verify current terms before acting.",
        summary="Sample fixture showing a low-cost research item. It is not a campaign or reward promise.",
    ),
    _sample(
        opportunity_id="sample-contribution",
        title="Sample: prepare a small ecosystem contribution",
        category="contribution",
        source_url="https://solana.com/developers",
        source_type="official_docs_example",
        capital_required_usd=0,
        estimated_human_minutes=90,
        reward_type="Potential recognition — demo only",
        reward_certainty="sample_only",
        deadline=date(2026, 10, 8),
        risk_level=RiskLevel.MEDIUM,
        components=ScoreComponents(
            expected_roi=12,
            evidence_quality=14,
            capital_efficiency=15,
            ai_leverage=11,
            strategic_value=14,
            risk=7,
        ),
        recommended_action="Draft locally; publish only after scope and source are verified.",
        summary="Sample fixture for a contribution workflow. It carries no verified reward or acceptance claim.",
    ),
    _sample(
        opportunity_id="sample-unverified-claim",
        title="Sample: inspect an unverified campaign claim",
        category="campaign",
        source_url="https://solana.com/",
        source_type="unverified_claim_example",
        capital_required_usd=25,
        estimated_human_minutes=60,
        reward_type="Unverified reward claim — demo only",
        reward_certainty="unverified",
        deadline=date(2026, 10, 1),
        risk_level=RiskLevel.HIGH,
        components=ScoreComponents(
            expected_roi=10,
            evidence_quality=4,
            capital_efficiency=5,
            ai_leverage=9,
            strategic_value=8,
            risk=3,
        ),
        recommended_action="Do not spend funds; verify primary evidence before considering it.",
        summary="Sample fixture deliberately marked high risk to demonstrate filtering and caution states.",
    ),
]


class InMemoryOpportunityRepository:
    def __init__(self, opportunities: list[Opportunity] | None = None) -> None:
        self._opportunities = opportunities or SAMPLE_OPPORTUNITIES

    def list(self, *, category: str | None = None, risk_level: RiskLevel | None = None) -> list[Opportunity]:
        results = self._opportunities
        if category:
            results = [item for item in results if item.category == category]
        if risk_level:
            results = [item for item in results if item.risk_level == risk_level]
        return sorted(results, key=lambda item: item.bcop_score, reverse=True)

    def get(self, opportunity_id: str) -> Opportunity | None:
        return next((item for item in self._opportunities if item.id == opportunity_id), None)
