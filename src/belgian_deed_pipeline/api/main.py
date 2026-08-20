"""FastAPI application exposing the loaded deed database.

The API intentionally stays thin: all SQL lives in belgian_deed_pipeline.db.queries so
the command-line tools and HTTP endpoints use the same business logic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from belgian_deed_pipeline.api.schemas import (
    CompanyProfileResponse,
    CompanySearchResult,
    DecisionMakerResponse,
    StatsResponse,
)
from belgian_deed_pipeline.config import load_database_url
from belgian_deed_pipeline.db.queries import (
    find_company_mentions_by_enterprise_number,
    get_company_profile,
    get_decision_makers,
    get_stats,
    search_companies_by_name,
)
from belgian_deed_pipeline.db.session import dispose_engine, get_session, init_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the DB engine once at startup and dispose it on shutdown."""

    init_engine(load_database_url())
    yield
    dispose_engine()


app = FastAPI(
    title="Belgian Deed Pipeline API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Return a simple health response for Docker/API smoke tests."""

    return {"status": "ok"}


@app.get("/stats", response_model=StatsResponse)
def stats(session: Session = Depends(get_session)) -> dict[str, int]:
    """Expose database row counts."""

    return get_stats(session)


@app.get("/companies/{enterprise_number}", response_model=CompanyProfileResponse)
def company_profile(
    enterprise_number: str,
    session: Session = Depends(get_session),
) -> dict:
    """Return all known company/deed/document rows for an enterprise number."""

    profile = get_company_profile(session, enterprise_number)
    if profile is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return profile


@app.get("/companies/{enterprise_number}/decision-makers", response_model=list[DecisionMakerResponse])
def decision_makers(
    enterprise_number: str,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[DecisionMakerResponse]:
    """Return non-notary party roles for the matched company/deeds."""

    rows = get_decision_makers(session, enterprise_number, limit=limit)
    return [
        DecisionMakerResponse(
            party_role=row.party_role,
            deed=row.deed,
            document=row.document,
        )
        for row in rows
    ]


@app.get("/search", response_model=list[CompanySearchResult])
def search(
    query: str = Query(min_length=2),
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[CompanySearchResult]:
    """Search companies by name."""

    rows = search_companies_by_name(session, query, limit=limit)
    return [
        CompanySearchResult(
            company=row.company,
            deed=row.deed,
            document=row.document,
        )
        for row in rows
    ]


@app.get("/companies/{enterprise_number}/mentions", response_model=list[CompanySearchResult])
def company_mentions(
    enterprise_number: str,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[CompanySearchResult]:
    """Return raw company mentions for an enterprise number."""

    rows = find_company_mentions_by_enterprise_number(
        session,
        enterprise_number,
        limit=limit,
    )
    return [
        CompanySearchResult(
            company=row.company,
            deed=row.deed,
            document=row.document,
        )
        for row in rows
    ]
