"""
Search for flight prices using fast-flights (Google Flights scraper).
Includes caching, rate limiting, and optional SerpAPI/SearchAPI fallbacks.

Uses a persistent Playwright browser to avoid re-launching per search.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, Page

from fast_flights import FlightData, Passengers, TFSData, Result, Flight
from fast_flights.core import parse_response

import config

load_dotenv()

# ── Module state ──────────────────────────────────────────────
_last_call_time: float = 0.0
_consecutive_failures: int = 0
_browser: Browser | None = None
_page: Page | None = None
_consent_accepted: bool = False
_playwright_ctx = None
_api_log: list[dict] = []


@dataclass
class FlightResult:
    provider: str           # "fast-flights", "serpapi", "searchapi"
    airline: str
    departure_airport: str  # IATA
    arrival_airport: str    # IATA
    departure_time: str
    arrival_time: str
    duration: str
    stops: int
    price_gbp: float
    is_best: bool
    search_date: str        # the date we searched for
    raw_price_str: str      # original price string


def _rate_limit(delay: float):
    """Enforce minimum delay between API calls."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_call_time = time.time()


def _log_call(provider: str, params: dict, status: str, result_count: int):
    """Append an entry to the in-memory API log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "provider": provider,
        "params": params,
        "status": status,
        "result_count": result_count,
    }
    _api_log.append(entry)


def save_api_log():
    """Write the accumulated API log to disk."""
    os.makedirs(config.DATA_DIR, exist_ok=True)

    existing = []
    if os.path.exists(config.API_LOG_PATH):
        try:
            with open(config.API_LOG_PATH) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    existing.extend(_api_log)
    with open(config.API_LOG_PATH, "w") as f:
        json.dump(existing, f, indent=2)


def get_api_log() -> list[dict]:
    """Return the in-memory log plus any existing on disk."""
    existing = []
    if os.path.exists(config.API_LOG_PATH):
        try:
            with open(config.API_LOG_PATH) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return existing + _api_log


# ── Persistent Playwright browser ─────────────────────────────
# Uses a dedicated thread with its own event loop to keep the browser alive
# across multiple sync calls.

import threading

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None


def _start_event_loop():
    """Run the event loop in a background thread forever."""
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()


def _run_async(coro):
    """Submit a coroutine to the persistent event loop and wait for the result."""
    global _loop, _thread
    if _loop is None or _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_start_event_loop, daemon=True)
        _thread.start()
        # Give the loop a moment to start
        import time as _t
        _t.sleep(0.1)
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=60)


async def _ensure_browser():
    """Launch a browser once and reuse it for all searches."""
    global _browser, _page, _playwright_ctx, _consent_accepted

    if _browser and _page:
        return

    print("  Launching persistent browser for flight searches...", flush=True)
    _playwright_ctx = await async_playwright().start()
    _browser = await _playwright_ctx.chromium.launch(headless=True)
    context = await _browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="en-GB",
    )
    _page = await context.new_page()

    # Navigate to Google Flights once to accept consent
    await _page.goto("https://www.google.com/travel/flights", wait_until="domcontentloaded", timeout=20000)
    await asyncio.sleep(1)

    if "consent.google" in _page.url:
        try:
            await _page.click('button:has-text("Accept all")', timeout=5000)
            await asyncio.sleep(1)
            _consent_accepted = True
            print("  Accepted Google cookie consent.", flush=True)
        except Exception:
            print("  Could not find consent button, continuing anyway...", flush=True)
    else:
        _consent_accepted = True
        print("  No consent wall encountered.", flush=True)


async def _fetch_flights_reuse_browser(url: str) -> str:
    """
    Navigate the persistent page to a Google Flights URL and extract results.
    Much faster than launching a new browser each time.
    """
    await _ensure_browser()

    await _page.goto(url, wait_until="domcontentloaded", timeout=20000)

    # Handle consent if it pops up again
    if "consent.google" in _page.url:
        try:
            await _page.click('button:has-text("Accept all")', timeout=3000)
            await asyncio.sleep(1)
        except Exception:
            pass

    # Wait for flight results to load (the .eQ35Ce class is the results container)
    try:
        locator = _page.locator(".eQ35Ce")
        await locator.wait_for(timeout=10000)
    except Exception:
        # Sometimes Google shows a different layout or an error
        await asyncio.sleep(2)

    body = await _page.evaluate(
        '() => { const el = document.querySelector(\'[role="main"]\'); return el ? el.innerHTML : document.body.innerHTML; }'
    )
    return body


async def _close_browser_async():
    """Clean up the persistent browser."""
    global _browser, _page, _playwright_ctx
    if _browser:
        await _browser.close()
        _browser = None
        _page = None
    if _playwright_ctx:
        await _playwright_ctx.stop()
        _playwright_ctx = None


def close_browser():
    """Public sync wrapper to close the browser and stop the event loop."""
    global _loop, _thread
    if _loop and _browser:
        try:
            _run_async(_close_browser_async())
        except Exception:
            pass
    if _loop:
        _loop.call_soon_threadsafe(_loop.stop)
        _loop = None
        _thread = None


def parse_price_to_gbp(price_str: str) -> float | None:
    """
    Parse price strings like '£45', '$67', '€55', 'GBP 45' to GBP float.
    Returns None if unparseable.
    """
    if not price_str:
        return None

    text = price_str.strip()
    numbers = re.findall(r"[\d,]+\.?\d*", text)
    if not numbers:
        return None

    amount = float(numbers[0].replace(",", ""))

    if "£" in text or "GBP" in text.upper():
        return round(amount, 2)
    elif "€" in text or "EUR" in text.upper():
        return round(amount * config.EUR_TO_GBP, 2)
    elif "$" in text or "USD" in text.upper():
        return round(amount * config.USD_TO_GBP, 2)
    else:
        # Default: assume GBP if searching from UK
        return round(amount, 2)


# ── Cache ─────────────────────────────────────────────────────

def _cache_path(from_iata: str, to_iata: str, search_date: str) -> str:
    return os.path.join(config.FLIGHT_CACHE_DIR, f"{from_iata}_{to_iata}_{search_date}.json")


def _is_cache_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours < config.FLIGHT_CACHE_TTL_HOURS


def _load_cache(path: str) -> list[FlightResult]:
    try:
        with open(path) as f:
            data = json.load(f)
        return [FlightResult(**item) for item in data]
    except (json.JSONDecodeError, IOError, TypeError):
        return []


def _save_cache(path: str, results: list[FlightResult]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)


# ── fast-flights provider ────────────────────────────────────

def search_fast_flights(from_iata: str, to_iata: str, search_date: str) -> list[FlightResult]:
    """
    Search using fast-flights' protobuf encoding + persistent Playwright browser.
    Reuses one browser for all searches (accepts consent once, then keeps going).
    """
    global _consecutive_failures

    _rate_limit(config.FAST_FLIGHTS_DELAY_SECONDS)

    params = {"from": from_iata, "to": to_iata, "date": search_date}

    try:
        # Build the protobuf-encoded URL using fast-flights' TFSData
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
        encoded = tfs.as_b64()
        url_params = {
            "tfs": encoded.decode("utf-8"),
            "hl": "en",
            "tfu": "EgQIABABIgA",
            "curr": "GBP",
        }
        url = "https://www.google.com/travel/flights?" + "&".join(
            f"{k}={v}" for k, v in url_params.items()
        )

        # Fetch using persistent browser (much faster than launching new browser each time)
        body = _run_async(_fetch_flights_reuse_browser(url))

        # Parse using fast-flights' parser
        class DummyResponse:
            status_code = 200
            text = body
            text_markdown = body

        result: Result = parse_response(DummyResponse())

        flights = []
        for f in result.flights:
            price = parse_price_to_gbp(f.price)
            if price is None or price <= 0:
                continue
            if not f.name or not f.name.strip():
                continue

            flights.append(FlightResult(
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
            ))

        _consecutive_failures = 0
        _log_call("fast-flights", params, "ok", len(flights))
        return flights

    except Exception as e:
        _consecutive_failures += 1
        error_msg = str(e)[:200]  # Truncate long error messages
        _log_call("fast-flights", params, f"error: {error_msg}", 0)
        if _consecutive_failures <= 3:
            print(f"    fast-flights error for {from_iata}->{to_iata}: {error_msg[:80]}")
        return []


# ── SerpAPI fallback ──────────────────────────────────────────

def search_serpapi(from_iata: str, to_iata: str, search_date: str) -> list[FlightResult]:
    """Fallback: use SerpAPI Google Flights endpoint."""
    api_key = os.getenv("SERPAPI_KEY", "").strip()
    if not api_key:
        return []

    _rate_limit(config.API_DELAY_SECONDS)
    params = {
        "engine": "google_flights",
        "departure_id": from_iata,
        "arrival_id": to_iata,
        "outbound_date": search_date,
        "type": "2",  # one-way
        "currency": "GBP",
        "hl": "en",
        "api_key": api_key,
    }

    try:
        resp = httpx.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        flights = []
        for option in data.get("best_flights", []) + data.get("other_flights", []):
            for leg in option.get("flights", []):
                price_val = option.get("price")
                if price_val is None:
                    continue

                flights.append(FlightResult(
                    provider="serpapi",
                    airline=leg.get("airline", "Unknown"),
                    departure_airport=leg.get("departure_airport", {}).get("id", from_iata),
                    arrival_airport=leg.get("arrival_airport", {}).get("id", to_iata),
                    departure_time=leg.get("departure_airport", {}).get("time", ""),
                    arrival_time=leg.get("arrival_airport", {}).get("time", ""),
                    duration=str(option.get("total_duration", "")),
                    stops=len(option.get("flights", [])) - 1,
                    price_gbp=float(price_val),
                    is_best="best_flights" in str(data.get("best_flights", [])),
                    search_date=search_date,
                    raw_price_str=f"£{price_val}",
                ))
                break  # Only take the first leg info per option

        _log_call("serpapi", {"from": from_iata, "to": to_iata, "date": search_date}, "ok", len(flights))
        return flights

    except Exception as e:
        _log_call("serpapi", {"from": from_iata, "to": to_iata, "date": search_date}, f"error: {e}", 0)
        return []


# ── SearchAPI fallback ────────────────────────────────────────

def search_searchapi(from_iata: str, to_iata: str, search_date: str) -> list[FlightResult]:
    """Fallback: use SearchAPI Google Flights endpoint."""
    api_key = os.getenv("SEARCHAPI_KEY", "").strip()
    if not api_key:
        return []

    _rate_limit(config.API_DELAY_SECONDS)
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
        resp = httpx.get("https://www.searchapi.io/api/v1/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        flights = []
        for option in data.get("best_flights", []) + data.get("other_flights", []):
            for leg in option.get("flights", []):
                price_val = option.get("price")
                if price_val is None:
                    continue

                flights.append(FlightResult(
                    provider="searchapi",
                    airline=leg.get("airline", "Unknown"),
                    departure_airport=leg.get("departure_airport", {}).get("id", from_iata),
                    arrival_airport=leg.get("arrival_airport", {}).get("id", to_iata),
                    departure_time=leg.get("departure_airport", {}).get("time", ""),
                    arrival_time=leg.get("arrival_airport", {}).get("time", ""),
                    duration=str(option.get("total_duration", "")),
                    stops=len(option.get("flights", [])) - 1,
                    price_gbp=float(price_val),
                    is_best=False,
                    search_date=search_date,
                    raw_price_str=f"£{price_val}",
                ))
                break

        _log_call("searchapi", {"from": from_iata, "to": to_iata, "date": search_date}, "ok", len(flights))
        return flights

    except Exception as e:
        _log_call("searchapi", {"from": from_iata, "to": to_iata, "date": search_date}, f"error: {e}", 0)
        return []


# ── Search with fallback chain ────────────────────────────────

def search_with_fallback(from_iata: str, to_iata: str, search_date: str) -> list[FlightResult]:
    """Try providers in order: fast-flights -> serpapi -> searchapi."""
    results = search_fast_flights(from_iata, to_iata, search_date)
    if results:
        return results

    results = search_serpapi(from_iata, to_iata, search_date)
    if results:
        return results

    results = search_searchapi(from_iata, to_iata, search_date)
    return results


def search_with_cache(from_iata: str, to_iata: str, search_date: str) -> list[FlightResult]:
    """Check cache first, then search with fallback chain."""
    path = _cache_path(from_iata, to_iata, search_date)
    if _is_cache_fresh(path):
        cached = _load_cache(path)
        if cached is not None:
            return cached

    results = search_with_fallback(from_iata, to_iata, search_date)
    # Always save to cache (even empty results) to avoid re-searching
    _save_cache(path, results)
    return results


# ── Per-deal search orchestration ─────────────────────────────

def search_flights_for_deal(deal: dict) -> dict:
    """
    Given a filtered Imoova deal, search for outbound and return flights.
    Returns an enriched deal dict with flight options and total cost.
    """
    pickup_city = deal["pickup_city"]
    dropoff_city = deal["dropoff_city"]
    depart_date = date.fromisoformat(deal["depart_date"])
    deliver_date = date.fromisoformat(deal["deliver_date"])

    warnings = []
    outbound_flights = []
    return_flights = []
    outbound_uk_transport = None
    return_uk_transport = None

    # ── Determine if we need outbound/return flights ──────────
    pickup_is_london = config.is_london(pickup_city)
    dropoff_is_london = config.is_london(dropoff_city)
    pickup_is_uk = config.is_uk_city(pickup_city)
    dropoff_is_uk = config.is_uk_city(dropoff_city)

    # ── Outbound: London -> Pickup City ───────────────────────
    if pickup_is_london:
        # No outbound flight needed
        pass
    elif pickup_is_uk and not pickup_is_london:
        # UK city, not London: handle via uk_transport module (imported in main)
        # For now, search domestic flights
        outbound_uk_transport = _search_uk_leg(pickup_city, "from_london", depart_date)
    else:
        # International: fly from London to pickup city
        pickup_airports = config.get_airports_for_city(pickup_city)
        if not pickup_airports:
            warnings.append(f"No airport mapping for pickup city '{pickup_city}'")
        else:
            outbound_dates = _get_search_dates(depart_date, direction="before")
            outbound_flights = _search_multi_airport(
                from_airports=config.LONDON_PRIORITY_AIRPORTS,
                to_airports=pickup_airports,
                dates=outbound_dates,
            )
            if not outbound_flights:
                warnings.append(f"No outbound flights found to {pickup_city}")

    # ── Return: Dropoff City -> London ────────────────────────
    if dropoff_is_london:
        # No return flight needed
        pass
    elif dropoff_is_uk and not dropoff_is_london:
        return_uk_transport = _search_uk_leg(dropoff_city, "to_london", deliver_date)
    else:
        dropoff_airports = config.get_airports_for_city(dropoff_city)
        if not dropoff_airports:
            warnings.append(f"No airport mapping for dropoff city '{dropoff_city}'")
        else:
            return_dates = _get_search_dates(deliver_date, direction="after")
            return_flights = _search_multi_airport(
                from_airports=dropoff_airports,
                to_airports=config.LONDON_PRIORITY_AIRPORTS,
                dates=return_dates,
            )
            if not return_flights:
                warnings.append(f"No return flights found from {dropoff_city}")

    # ── Sort and pick cheapest ────────────────────────────────
    outbound_flights.sort(key=lambda f: f.price_gbp)
    return_flights.sort(key=lambda f: f.price_gbp)

    cheapest_out = outbound_flights[0] if outbound_flights else None
    cheapest_ret = return_flights[0] if return_flights else None

    # ── Calculate total cost (per person: half the Imoova fee) ─
    total = deal["rate_gbp"] / 2

    if cheapest_out:
        total += cheapest_out.price_gbp
    elif outbound_uk_transport:
        total += outbound_uk_transport.get("price_gbp", 0)

    if cheapest_ret:
        total += cheapest_ret.price_gbp
    elif return_uk_transport:
        total += return_uk_transport.get("price_gbp", 0)

    # If we couldn't find any transport for a required leg, mark as incomplete
    needs_outbound = not pickup_is_london
    needs_return = not dropoff_is_london
    is_complete = True

    if needs_outbound and not cheapest_out and not outbound_uk_transport:
        is_complete = False
    if needs_return and not cheapest_ret and not return_uk_transport:
        is_complete = False

    return {
        "deal": deal,
        "outbound_flights": [asdict(f) for f in outbound_flights[:3]],
        "return_flights": [asdict(f) for f in return_flights[:3]],
        "outbound_uk_transport": outbound_uk_transport,
        "return_uk_transport": return_uk_transport,
        "cheapest_outbound": asdict(cheapest_out) if cheapest_out else None,
        "cheapest_return": asdict(cheapest_ret) if cheapest_ret else None,
        "total_cost": round(total, 2),
        "is_complete": is_complete,
        "warnings": warnings,
    }


def _get_search_dates(ref_date: date, direction: str) -> list[str]:
    """
    Return 2-3 dates to search around the reference date.
    direction='before': [ref_date - 1, ref_date]
    direction='after': [ref_date, ref_date + 1]
    Clamps to travel window.
    """
    dates = []
    if direction == "before":
        candidates = [ref_date - timedelta(days=1), ref_date]
    else:
        candidates = [ref_date, ref_date + timedelta(days=1)]

    for d in candidates:
        if config.TRAVEL_WINDOW_START <= d <= config.TRAVEL_WINDOW_END:
            dates.append(d.isoformat())

    return dates if dates else [ref_date.isoformat()]


def _search_multi_airport(
    from_airports: list[str],
    to_airports: list[str],
    dates: list[str],
) -> list[FlightResult]:
    """
    Search all combinations of from_airport x to_airport x date.
    Returns deduplicated results sorted by price.
    """
    all_results = []
    seen = set()

    for from_apt in from_airports:
        for to_apt in to_airports:
            for d in dates:
                results = search_with_cache(from_apt, to_apt, d)
                for r in results:
                    key = (r.airline, r.departure_time, r.price_gbp, r.search_date)
                    if key not in seen:
                        seen.add(key)
                        all_results.append(r)

    all_results.sort(key=lambda f: f.price_gbp)
    return all_results


def _search_uk_leg(uk_city: str, direction: str, ref_date: date) -> dict | None:
    """
    Search for domestic transport between a UK city and London.
    Returns the cheapest option (flight or train estimate).
    """
    city_airports = config.get_airports_for_city(uk_city)
    dates = [ref_date.isoformat()]

    cheapest_flight = None

    if city_airports:
        if direction == "to_london":
            flights = _search_multi_airport(city_airports, config.LONDON_PRIORITY_AIRPORTS, dates)
        else:
            flights = _search_multi_airport(config.LONDON_PRIORITY_AIRPORTS, city_airports, dates)

        if flights:
            cheapest_flight = flights[0]

    # Get train estimate
    train_price = config.UK_TRAIN_ESTIMATES.get(uk_city)

    # Compare and return cheaper
    if cheapest_flight and train_price:
        if cheapest_flight.price_gbp <= train_price:
            return {
                "mode": "flight",
                "price_gbp": cheapest_flight.price_gbp,
                "details": f"{cheapest_flight.airline} {cheapest_flight.departure_airport}->{cheapest_flight.arrival_airport} £{cheapest_flight.price_gbp:.0f}",
                "is_estimate": False,
            }
        else:
            return {
                "mode": "train_estimate",
                "price_gbp": train_price,
                "details": f"Train {uk_city}->London £{train_price:.0f} (ESTIMATE)",
                "is_estimate": True,
            }
    elif cheapest_flight:
        return {
            "mode": "flight",
            "price_gbp": cheapest_flight.price_gbp,
            "details": f"{cheapest_flight.airline} {cheapest_flight.departure_airport}->{cheapest_flight.arrival_airport} £{cheapest_flight.price_gbp:.0f}",
            "is_estimate": False,
        }
    elif train_price:
        return {
            "mode": "train_estimate",
            "price_gbp": train_price,
            "details": f"Train {uk_city}->London £{train_price:.0f} (ESTIMATE)",
            "is_estimate": True,
        }

    return None


def presearch_unique_routes(filtered_deals: list[dict]):
    """
    Pre-search all unique (airport, airport, date) combos across all deals.
    This fills the cache so that individual deal searches read from cache instantly.
    Much faster than searching per-deal because many deals share routes.
    """
    unique_searches = set()

    for deal in filtered_deals:
        pickup = deal["pickup_city"]
        dropoff = deal["dropoff_city"]
        depart = date.fromisoformat(deal["depart_date"])
        deliver = date.fromisoformat(deal["deliver_date"])

        # Outbound: London -> Pickup City
        if not config.is_london(pickup):
            airports = config.get_airports_for_city(pickup)
            if airports:
                out_dates = _get_search_dates(depart, "before")
                for apt in airports:
                    for london in config.LONDON_PRIORITY_AIRPORTS:
                        for d in out_dates:
                            unique_searches.add((london, apt, d))

        # Return: Dropoff City -> London
        if not config.is_london(dropoff):
            airports = config.get_airports_for_city(dropoff)
            if airports:
                ret_dates = _get_search_dates(deliver, "after")
                for apt in airports:
                    for london in config.LONDON_PRIORITY_AIRPORTS:
                        for d in ret_dates:
                            unique_searches.add((apt, london, d))

    # Filter out already-cached routes
    uncached = []
    for from_apt, to_apt, d in unique_searches:
        path = _cache_path(from_apt, to_apt, d)
        if not _is_cache_fresh(path):
            uncached.append((from_apt, to_apt, d))

    total_unique = len(unique_searches)
    already_cached = total_unique - len(uncached)
    print(f"  {total_unique} unique routes, {already_cached} already cached, "
          f"{len(uncached)} to search")

    if not uncached:
        return

    est_minutes = len(uncached) * 8 / 60
    print(f"  Estimated time: ~{est_minutes:.0f} minutes ({len(uncached)} searches x ~8s each)")
    print()

    for i, (from_apt, to_apt, d) in enumerate(uncached, 1):
        if i % 10 == 1 or i == len(uncached):
            print(f"  Searching {i}/{len(uncached)}: {from_apt}->{to_apt} on {d}...")
        search_with_cache(from_apt, to_apt, d)

    print(f"  Pre-search complete.")


def search_all_deals(filtered_deals: list[dict]) -> list[dict]:
    """
    Search flights for every filtered deal. Returns enriched deals sorted by total cost.
    First pre-searches all unique routes, then assembles results per deal from cache.
    """
    # Phase 1: Pre-search unique routes
    print("  Phase 1: Pre-searching unique flight routes...")
    presearch_unique_routes(filtered_deals)
    print()

    # Phase 2: Assemble results per deal (all reads from cache, very fast)
    print("  Phase 2: Assembling results per deal...")
    enriched = []
    total = len(filtered_deals)

    for i, deal in enumerate(filtered_deals, 1):
        if i % 20 == 1 or i == total:
            print(f"  [{i}/{total}] {deal['pickup_city']} -> {deal['dropoff_city']}...")

        try:
            result = search_flights_for_deal(deal)
            enriched.append(result)
        except Exception as e:
            print(f"    Error: {e}")
            enriched.append({
                "deal": deal,
                "outbound_flights": [],
                "return_flights": [],
                "outbound_uk_transport": None,
                "return_uk_transport": None,
                "cheapest_outbound": None,
                "cheapest_return": None,
                "total_cost": 9999.0,
                "is_complete": False,
                "warnings": [f"Search failed: {e}"],
            })

    # Save the API log
    save_api_log()

    # Sort by total cost
    enriched.sort(key=lambda x: x["total_cost"])
    return enriched


if __name__ == "__main__":
    # Quick test: search one route
    print("=== Flight Search Test ===\n")
    print("Searching STN -> BCN on 2026-03-28...")
    results = search_with_cache("STN", "BCN", "2026-03-28")
    if results:
        print(f"Found {len(results)} flights:")
        for r in results[:5]:
            print(f"  {r.airline} | {r.departure_time} -> {r.arrival_time} | "
                  f"{r.stops} stops | {r.raw_price_str} (£{r.price_gbp:.2f})")
    else:
        print("  No results found")
    save_api_log()
