from __future__ import annotations

from typing import Annotated

from app.config import settings
from app.models import Opportunity, RiskLevel
from app.repository import InMemoryOpportunityRepository
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

repository = InMemoryOpportunityRepository()

app = FastAPI(
    title="PipiShrimp Alpha API",
    version="0.1.0",
    description="Read-only sample opportunity feed for BCOP-CODEX-0002.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["health"])
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "pipishrimp-backend"}


@app.get("/v1/opportunities", response_model=list[Opportunity], tags=["opportunities"])
def list_opportunities(
    category: Annotated[str | None, Query(min_length=1)] = None,
    risk_level: Annotated[RiskLevel | None, Query()] = None,
) -> list[Opportunity]:
    return repository.list(category=category, risk_level=risk_level)


@app.get("/v1/opportunities/{opportunity_id}", response_model=Opportunity, tags=["opportunities"])
def get_opportunity(opportunity_id: str) -> Opportunity:
    opportunity = repository.get(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity
