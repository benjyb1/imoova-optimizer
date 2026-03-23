"""
Search for flight prices using fast-flights (Google Flights scraper).
Includes caching, rate limiting, and optional SerpAPI/SearchAPI fallbacks.

Uses primp HTTP client with consent cookies — no browser/Playwright needed.
Adapted from the original search_flights.py for the async FastAPI backend.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple

import httpx
from dotenv import load_dotenv
from primp import Client as PrimpClient

from fast_flights import FlightData, Passengers, TFSData, Result
from fast_flights.core import parse_response

import config

load_dotenv()
logger = logging.getLogger(__name__)

# ── Module state (per-process, shared across jobs) ────────────
_last_call_time: float = 0.0
_consecutive_failures: int = 0
_primp_client: Optional[PrimpClient] = None


@dataclass
class FlightResult:
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


# ── Rate limiting ─────────────────────────────────────────────

async def _rate_limit(delay: float) -> None:
    """Enforce minimum delay between API calls."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < delay:
        await asyncio.sleep(delay - elapsed)
    _last_call_time = time.time()


# ── HTTP client with Google consent cookies (no browser needed) ─

def _get_primp_client() -> PrimpClient:
    """Get or create a primp HTTP client with consent cookies set."""
    global _primp_client
    if _primp_client is None:
        _primp_client = PrimpClient(impersonate="chrome_126", verify=False)
        # Set Google consent cookies to bypass the consent wall
        _primp_client.set_cookies("https://www.google.com", {
            "SOCS": "CAESEwgDEgk2MjY0Mzc0MzIaAmVuIAEaBgiA_OCyBg",
            "CONSENT": "YES+",
        })
        logger.info("Initialised primp HTTP client with consent cookies.")
    return _primp_client


async def close_browser() -> None:
    """No-op for backwards compatibility — no browser to close."""
    global _primp_client
    _primp_client = None


def parse_price_to_gbp(price_str: str) -> Optional[float]:
    """Parse price strings like '\u00a345', '$67', '\u20ac55' to GBP float."""
    if not price_str:
        return None
    text = price_str.strip()
    numbers = re.findall(r"[\d,]+\.?\d*", text)
    if not numbers:
        return None
    amount = float(numbers[0].replace(",", ""))

    if "\u00a3" in text or "GBP" in text.upper():
        return round(amount, 2)
    elif "\u20ac" in text or "EUR" in text.upper():
        return round(amount * config.EUR_TO_GBP, 2)
    elif "$" in text or "USD" in text.upper():
        return round(amount * config.USD_TO_GBP, 2)
    else:
        return round(amount, 2)


# ── Cache ─────────────────────────────────────────────────────

def _cache_path(from_iata: str, to_iata: str, search_date: str) -> str:
    return os.path.join(
        config.FLIGHT_CACHE_DIR, f"{from_iata}_{to_iata}_{search_date}.json"
    )


def _is_cache_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours < config.FLIGHT_CACHE_TTL_HOURS


def _load_cache(path: str) -> List[FlightResult]:
    try:
        with open(path) as f:
            data = json.load(f)
        return [FlightResult(**item) for item in data]
    except (json.JSONDecodeError, IOError, TypeError):
        return []


def _save_cache(path: str, results: List[FlightResult]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)


# ── fast-flights provider ────────────────────────────────────

async def search_fast_flights(
    from_iata: str, to_iata: str, search_date: str
) -> List[FlightResult]:
    """
    Search using fast-flights protobuf encoding + primp HTTP client.
    No browser needed — uses consent cookies to bypass Google's wall.
    """
    global _consecutive_failures

    await _rate_limit(config.FAST_FLIGHTS_DELAY_SECONDS)

    try:
        tfs = TFSData.from_interface(
            flight_data=[
                FlightData(
                    date=search_date,
                    from_airport=from_iata,
                    to_airport=to_iata,
                    max_stops=1,
                )
            ],
            trip="one-way",
            passengers=Passengers(adults=1),
            seat="economy",
        )
        params = {
            "tfs": tfs.as_b64().decode("utf-8"),
            "hl": "en",
            "tfu": "EgQIABABIgA",
            "curr": "GBP",
        }

        # Use primp HTTP client (runs in thread pool to avoid blocking event loop)
        client = _get_primp_client()
        res = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.get("https://www.google.com/travel/flights", params=params),
        )

        if res.status_code != 200:
            logger.warning(
                "Google Flights returned %d for %s->%s", res.status_code, from_iata, to_iata
            )
            return []

        # Check for consent wall in response
        if "Before you continue" in res.text[:1000]:
            logger.warning("Hit consent wall for %s->%s, resetting client", from_iata, to_iata)
            global _primp_client
            _primp_client = None  # Force re-creation with fresh cookies
            return []

        result: Result = parse_response(res)

        flights: List[FlightResult] = []
        for f in result.flights:
            price = parse_price_to_gbp(f.price)
            if price is None or price <= 0:
                continue
            if not f.name or not f.name.strip():
                continue

            flights.append(
                FlightResult(
                    provider="fast-flights",
                    airline=f.name,
                    departure_airport=from_iata,
                    arrival_airport=to_iata,
                    departure_time=f.departure,
                    arrival_time=f.arrival,
                    duration=f.duration,
                    stops=f.stops,
                    price_gbp=price,
                    is_best=f.is_best,
                    search_date=search_date,
                    raw_price_str=f.price,
                )
            )

        _consecutive_failures = 0
        return flights

    except Exception as e:
        _consecutive_failures += 1
        error_msg = str(e)[:200]
        if _consecutive_failures <= 3:
            logger.warning(
                "fast-flights error for %s->%s: %s", from_iata, to_iata, error_msg[:80]
            )
        return []


# ── SerpAPI fallback ──────────────────────────────────────────

async def search_serpapi(
    from_iata: str, to_iata: str, search_date: str
) -> List[FlightResult]:
    """Fallback: use SerpAPI Google Flights endpoint."""
    api_key = os.getenv("SERPAPI_KEY", "").strip()
    if not api_key:
        return []

    await _rate_limit(config.API_DELAY_SECONDS)
    params = {
        "engine": "google_flights",
        "departure_id": from_iata,
        "arrival_id": to_iata,
        "outbound_date": search_date,
        "type": "2",
        "currency": "GBP",
        "hl": "en",
        "api_key": api_key,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://serpapi.com/search", params=params, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

        flights: List[FlightResult] = []
        for option in data.get("best_flights", []) + data.get("other_flights", []):
            for leg in option.get("flights", []):
                price_val = option.get("price")
                if price_val is None:
                    continue
                flights.append(
                    FlightResult(
                        provider="serpapi",
                        airline=leg.get("airline", "Unknown"),
                        departure_airport=leg.get("departure_airport", {}).get(
                            "id", from_iata
                        ),
                        arrival_airport=leg.get("arrival_airport", {}).get(
                            "id", to_iata
                        ),
                        departure_time=leg.get("departure_airport", {}).get(
                            "time", ""
                        ),
                        arrival_time=leg.get("arrival_airport", {}).get("time", ""),
                        duration=str(option.get("total_duration", "")),
                        stops=len(option.get("flights", [])) - 1,
                        price_gbp=float(price_val),
                        is_best=False,
                        search_date=search_date,
                        raw_price_str=f"\u00a3{price_val}",
                    )
                )
                break
        return flights

    except Exception as e:
        logger.warning("serpapi error for %s->%s: %s", from_iata, to_iata, e)
        return []


# ── SearchAPI fallback ────────────────────────────────────────

async def search_searchapi(
    from_iata: str, to_iata: str, search_date: str
) -> List[FlightResult]:
    """Fallback: use SearchAPI Google Flights endpoint."""
    api_key = os.getenv("SEARCHAPI_KEY", "").strip()
    if not api_key:
        return []

    await _rate_limit(config.API_DELAY_SECONDS)
    params = {
        "engine": "google_flights",
        "departure_id": from_iata,
        "arrival_id": to_iata,
        "outbound_date": search_date,
        "type": "2",
        "currency": "GBP",
        "hl": "en",
        "api_key": api_key,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.searchapi.io/api/v1/search", params=params, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

        flights: List[FlightResult] = []
        for option in data.get("best_flights", []) + data.get("other_flights", []):
            for leg in option.get("flights", []):
                price_val = option.get("price")
                if price_val is None:
                    continue
                flights.append(
                    FlightResult(
                        provider="searchapi",
                        airline=leg.get("airline", "Unknown"),
                        departure_airport=leg.get("departure_airport", {}).get(
                            "id", from_iata
                        ),
                        arrival_airport=leg.get("arrival_airport", {}).get(
                            "id", to_iata
                        ),
                        departure_time=leg.get("departure_airport", {}).get(
                            "time", ""
                        ),
                        arrival_time=leg.get("arrival_airport", {}).get("time", ""),
                        duration=str(option.get("total_duration", "")),
                        stops=len(option.get("flights", [])) - 1,
                        price_gbp=float(price_val),
                        is_best=False,
                        search_date=search_date,
                        raw_price_str=f"\u00a3{price_val}",
                    )
                )
                break
        return flights

    except Exception as e:
        logger.warning("searchapi error for %s->%s: %s", from_iata, to_iata, e)
        return []


# ── Search with fallback chain ────────────────────────────────

async def search_with_fallback(
    from_iata: str, to_iata: str, search_date: str
) -> List[FlightResult]:
    """Try providers in order: fast-flights -> serpapi -> searchapi."""
    results = await search_fast_flights(from_iata, to_iata, search_date)
    if results:
        return results

    results = await search_serpapi(from_iata, to_iata, search_date)
    if results:
        return results

    results = await search_searchapi(from_iata, to_iata, search_date)
    return results


async def search_with_cache(
    from_iata: str, to_iata: str, search_date: str
) -> List[FlightResult]:
    """Check cache first, then search with fallback chain."""
    path = _cache_path(from_iata, to_iata, search_date)
    if _is_cache_fresh(path):
        cached = _load_cache(path)
        if cached:
            return cached

    results = await search_with_fallback(from_iata, to_iata, search_date)
    if results:
        _save_cache(path, results)
    return results


# ── Per-deal search orchestration ─────────────────────────────

def _get_search_dates(ref_date: date, direction: str) -> List[str]:
    """
    Return 2 dates to search around the reference date.
    direction='before': [ref_date - 1, ref_date]
    direction='after': [ref_date, ref_date + 1]
    """
    if direction == "before":
        candidates = [ref_date - timedelta(days=1), ref_date]
    else:
        candidates = [ref_date, ref_date + timedelta(days=1)]

    return [d.isoformat() for d in candidates]


async def _search_multi_airport(
    from_airports: List[str],
    to_airports: List[str],
    dates: List[str],
) -> List[FlightResult]:
    """
    Search all combinations of from_airport x to_airport x date.
    Returns deduplicated results sorted by price.
    """
    all_results: List[FlightResult] = []
    seen: Set[Tuple[str, str, float, str]] = set()

    for from_apt in from_airports:
        for to_apt in to_airports:
            for d in dates:
                results = await search_with_cache(from_apt, to_apt, d)
                for r in results:
                    key = (r.airline, r.departure_time, r.price_gbp, r.search_date)
                    if key not in seen:
                        seen.add(key)
                        all_results.append(r)

    all_results.sort(key=lambda f: f.price_gbp)
    return all_results


async def _search_uk_leg(
    uk_city: str, direction: str, ref_date: date, home_airports: List[str]
) -> Optional[Dict[str, Any]]:
    """
    Search for domestic transport between a UK city and the user's home airports.
    Returns the cheapest option (flight or train estimate).
    """
    city_airports = config.get_airports_for_city(uk_city)
    dates = [ref_date.isoformat()]

    cheapest_flight: Optional[FlightResult] = None

    if city_airports:
        if direction == "to_home":
            flights = await _search_multi_airport(city_airports, home_airports, dates)
        else:
            flights = await _search_multi_airport(home_airports, city_airports, dates)

        if flights:
            cheapest_flight = flights[0]

    # Get train estimate (only applicable if home is London and city is UK)
    train_price = config.UK_TRAIN_ESTIMATES.get(uk_city)

    if cheapest_flight and train_price:
        if cheapest_flight.price_gbp <= train_price:
            return {
                "mode": "flight",
                "price_gbp": cheapest_flight.price_gbp,
                "details": (
                    f"{cheapest_flight.airline} "
                    f"{cheapest_flight.departure_airport}->"
                    f"{cheapest_flight.arrival_airport} "
                    f"\u00a3{cheapest_flight.price_gbp:.0f}"
                ),
                "is_estimate": False,
            }
        else:
            return {
                "mode": "train_estimate",
                "price_gbp": train_price,
                "details": f"Train {uk_city}->London \u00a3{train_price:.0f} (ESTIMATE)",
                "is_estimate": True,
            }
    elif cheapest_flight:
        return {
            "mode": "flight",
            "price_gbp": cheapest_flight.price_gbp,
            "details": (
                f"{cheapest_flight.airline} "
                f"{cheapest_flight.departure_airport}->"
                f"{cheapest_flight.arrival_airport} "
                f"\u00a3{cheapest_flight.price_gbp:.0f}"
            ),
            "is_estimate": False,
        }
    elif train_price:
        return {
            "mode": "train_estimate",
            "price_gbp": train_price,
            "details": f"Train {uk_city}->London \u00a3{train_price:.0f} (ESTIMATE)",
            "is_estimate": True,
        }

    return None


async def search_flights_for_deal(
    deal: Dict[str, Any],
    home_city: str,
    home_airports: List[str],
) -> Dict[str, Any]:
    """
    Given a filtered Imoova deal, search for outbound and return flights.
    Returns an enriched deal dict with flight options and total cost.

    Handles the case where home_city matches pickup or dropoff city
    (skip that flight leg, cost = 0).
    """
    pickup_city = deal["pickup_city"]
    dropoff_city = deal["dropoff_city"]
    depart_date = date.fromisoformat(deal["depart_date"])
    deliver_date = date.fromisoformat(deal["deliver_date"])

    warnings: List[str] = []
    outbound_flights: List[FlightResult] = []
    return_flights: List[FlightResult] = []
    outbound_uk_transport: Optional[Dict[str, Any]] = None
    return_uk_transport: Optional[Dict[str, Any]] = None

    # Check if home city matches pickup or dropoff
    home_is_pickup = config.cities_match(home_city, pickup_city)
    home_is_dropoff = config.cities_match(home_city, dropoff_city)

    pickup_is_uk = config.is_uk_city(pickup_city)
    dropoff_is_uk = config.is_uk_city(dropoff_city)

    # ── Outbound: Home -> Pickup City ─────────────────────────
    if home_is_pickup:
        # No outbound flight needed
        pass
    elif pickup_is_uk and not home_is_pickup:
        outbound_uk_transport = await _search_uk_leg(
            pickup_city, "from_home", depart_date, home_airports
        )
    else:
        pickup_airports = config.get_airports_for_city(pickup_city)
        if not pickup_airports:
            warnings.append(f"No airport mapping for pickup city '{pickup_city}'")
        else:
            outbound_dates = _get_search_dates(depart_date, direction="before")
            outbound_flights = await _search_multi_airport(
                from_airports=home_airports,
                to_airports=pickup_airports,
                dates=outbound_dates,
            )
            if not outbound_flights:
                warnings.append(f"No outbound flights found to {pickup_city}")

    # ── Return: Dropoff City -> Home ──────────────────────────
    if home_is_dropoff:
        # No return flight needed
        pass
    elif dropoff_is_uk and not home_is_dropoff:
        return_uk_transport = await _search_uk_leg(
            dropoff_city, "to_home", deliver_date, home_airports
        )
    else:
        dropoff_airports = config.get_airports_for_city(dropoff_city)
        if not dropoff_airports:
            warnings.append(f"No airport mapping for dropoff city '{dropoff_city}'")
        else:
            return_dates = _get_search_dates(deliver_date, direction="after")
            return_flights = await _search_multi_airport(
                from_airports=dropoff_airports,
                to_airports=home_airports,
                dates=return_dates,
            )
            if not return_flights:
                warnings.append(f"No return flights found from {dropoff_city}")

    # ── Sort and pick cheapest ────────────────────────────────
    outbound_flights.sort(key=lambda f: f.price_gbp)
    return_flights.sort(key=lambda f: f.price_gbp)

    cheapest_out = outbound_flights[0] if outbound_flights else None
    cheapest_ret = return_flights[0] if return_flights else None

    # ── Calculate total cost ──────────────────────────────────
    total = deal["rate_gbp"]

    if cheapest_out:
        total += cheapest_out.price_gbp
    elif outbound_uk_transport:
        total += outbound_uk_transport.get("price_gbp", 0)

    if cheapest_ret:
        total += cheapest_ret.price_gbp
    elif return_uk_transport:
        total += return_uk_transport.get("price_gbp", 0)

    # Determine completeness
    needs_outbound = not home_is_pickup
    needs_return = not home_is_dropoff
    is_complete = True

    if needs_outbound and not cheapest_out and not outbound_uk_transport:
        is_complete = False
    if needs_return and not cheapest_ret and not return_uk_transport:
        is_complete = False

    drive_hours = config.estimate_driving_hours(
        deal.get("pickup_city", ""), deal.get("dropoff_city", "")
    )

    # ── Build Google Flights URLs ──────────────────────────────
    def _google_flights_url(from_apts, to_apts, d):
        if not from_apts or not to_apts:
            return None
        return (
            f"https://www.google.com/travel/flights?q="
            f"Flights+from+{from_apts[0]}+to+{to_apts[0]}+on+{d}"
        )

    pickup_airports = config.get_airports_for_city(pickup_city) or []
    dropoff_airports = config.get_airports_for_city(dropoff_city) or []

    gf_outbound_url = None if home_is_pickup else _google_flights_url(
        home_airports, pickup_airports, depart_date.isoformat()
    )
    gf_return_url = None if home_is_dropoff else _google_flights_url(
        dropoff_airports, home_airports, deliver_date.isoformat()
    )

    # ── Reshape deal info to match frontend DealInfo interface ──
    deal_info = {
        "pickup_city": pickup_city,
        "pickup_country": config.CITY_COUNTRIES.get(pickup_city, ""),
        "dropoff_city": dropoff_city,
        "dropoff_country": config.CITY_COUNTRIES.get(dropoff_city, ""),
        "pickup_date": deal["depart_date"],
        "dropoff_date": deal["deliver_date"],
        "drive_days": deal.get("drive_days", 0),
        "vehicle_type": deal.get("vehicle", ""),
        "seats": deal.get("seats", 0),
        "imoova_price_gbp": deal.get("rate_gbp", 0),
        "imoova_url": deal.get("deal_url", ""),
    }

    return {
        "deal": deal_info,
        "drive_hours": drive_hours,
        "outbound_flight": asdict(cheapest_out) if cheapest_out else None,
        "return_flight": asdict(cheapest_ret) if cheapest_ret else None,
        "outbound_is_home": home_is_pickup,
        "return_is_home": home_is_dropoff,
        "total_price_gbp": round(total, 2) if is_complete else None,
        "google_flights_outbound_url": gf_outbound_url,
        "google_flights_return_url": gf_return_url,
        "is_complete": is_complete,
        "warnings": warnings,
    }


async def presearch_unique_routes(
    filtered_deals: List[Dict[str, Any]],
    home_airports: List[str],
    on_progress: Optional[Callable[[int, int], Coroutine[Any, Any, None]]] = None,
) -> None:
    """
    Pre-search all unique (airport, airport, date) combos across all deals.
    This fills the cache so that individual deal searches read from cache instantly.
    """
    unique_searches: Set[Tuple[str, str, str]] = set()

    for deal in filtered_deals:
        pickup = deal["pickup_city"]
        dropoff = deal["dropoff_city"]
        depart = date.fromisoformat(deal["depart_date"])
        deliver = date.fromisoformat(deal["deliver_date"])

        # Outbound: Home -> Pickup City
        if not config.cities_match("", pickup):  # always search unless home matches
            airports = config.get_airports_for_city(pickup)
            if airports:
                out_dates = _get_search_dates(depart, "before")
                for apt in airports:
                    for home_apt in home_airports:
                        for d in out_dates:
                            unique_searches.add((home_apt, apt, d))

        # Return: Dropoff City -> Home
        airports = config.get_airports_for_city(dropoff)
        if airports:
            ret_dates = _get_search_dates(deliver, "after")
            for apt in airports:
                for home_apt in home_airports:
                    for d in ret_dates:
                        unique_searches.add((apt, home_apt, d))

    # Filter out already-cached routes
    uncached: List[Tuple[str, str, str]] = []
    for from_apt, to_apt, d in unique_searches:
        path = _cache_path(from_apt, to_apt, d)
        if not _is_cache_fresh(path):
            uncached.append((from_apt, to_apt, d))

    total_unique = len(unique_searches)
    already_cached = total_unique - len(uncached)
    logger.info(
        "%d unique routes, %d already cached, %d to search",
        total_unique,
        already_cached,
        len(uncached),
    )

    if not uncached:
        return

    for i, (from_apt, to_apt, d) in enumerate(uncached, 1):
        if i % 10 == 1 or i == len(uncached):
            logger.info("Searching %d/%d: %s->%s on %s", i, len(uncached), from_apt, to_apt, d)
        await search_with_cache(from_apt, to_apt, d)
        if on_progress:
            await on_progress(i, len(uncached))

    logger.info("Pre-search complete.")
