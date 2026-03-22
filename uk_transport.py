"""
Handle UK domestic transport pricing for deals where pickup/dropoff
is a UK city that isn't London.

Compares domestic flights (via fast-flights) with train fare estimates
and returns whichever is cheaper.
"""

from __future__ import annotations

from datetime import date

import config
from search_flights import _search_multi_airport, _search_uk_leg


def get_uk_transport_cost(uk_city: str, direction: str, travel_date: date) -> dict | None:
    """
    Find the cheapest transport between a UK city and London.

    Args:
        uk_city: Name of the UK city (e.g. "Manchester")
        direction: "to_london" or "from_london"
        travel_date: The date of travel

    Returns:
        Dict with mode, price_gbp, details, is_estimate. Or None if no option found.
    """
    return _search_uk_leg(uk_city, direction, travel_date)


def is_uk_city(city_name: str) -> bool:
    """Check if a city is in the UK."""
    return config.is_uk_city(city_name)


def is_london(city_name: str) -> bool:
    """Check if a city is London."""
    return config.is_london(city_name)
