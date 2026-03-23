"""
Pydantic models for the Imoova Holiday Optimiser API.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    home_city: str
    min_days: int = Field(default=5, ge=1, le=30)
    max_days: int = Field(default=10, ge=1, le=30)
    min_seats: Optional[int] = Field(default=None, ge=1, le=10)
    earliest_departure: str = Field(default="")
    latest_return: str = Field(default="")

    @field_validator("earliest_departure", mode="before")
    @classmethod
    def default_earliest(cls, v: str) -> str:
        if not v:
            return (date.today() + timedelta(days=3)).isoformat()
        return v

    @field_validator("latest_return", mode="before")
    @classmethod
    def default_latest(cls, v: str) -> str:
        if not v:
            return (date.today() + timedelta(days=28)).isoformat()
        return v


class FlightResult(BaseModel):
    provider: str
    airline: str
    departure_airport: str
    arrival_airport: str
    departure_time: str
    arrival_time: str
    duration: str
    stops: int
    price_gbp: float
    is_best: bool
    search_date: str
    raw_price_str: str


class UkTransport(BaseModel):
    mode: str
    price_gbp: float
    details: str
    is_estimate: bool


class EnrichedDeal(BaseModel):
    deal: Dict[str, Any]
    outbound_flights: List[Dict[str, Any]] = Field(default_factory=list)
    return_flights: List[Dict[str, Any]] = Field(default_factory=list)
    outbound_uk_transport: Optional[Dict[str, Any]] = None
    return_uk_transport: Optional[Dict[str, Any]] = None
    cheapest_outbound: Optional[Dict[str, Any]] = None
    cheapest_return: Optional[Dict[str, Any]] = None
    total_cost: float
    is_complete: bool
    warnings: List[str] = Field(default_factory=list)


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued, scraping, filtering, searching, complete, error
    message: str = ""
    total_deals: int = 0
    searched_deals: int = 0
    total_results: int = 0
    complete_results: int = 0
    eta_seconds: Optional[float] = None
