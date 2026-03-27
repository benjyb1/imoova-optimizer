"""
Run the Imoova optimizer for London Gatwick (LGW) only.
Saves results to an Excel spreadsheet.

Usage: python run_gatwick.py
"""
import asyncio
import json
import os
import sys
import time

# Ensure root dir is first on path so 'import config' finds root config.py
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)
_backend = os.path.join(_root, "backend")
if _backend in sys.path:
    sys.path.remove(_backend)

from datetime import date

import config
from backend.scraper import scrape_all_deals, filter_deals
from backend.flights import (
    search_flights_for_deal,
    presearch_unique_routes,
    close_browser,
)
from build_spreadsheet import build_spreadsheet

# ── User parameters ──────────────────────────────────────────
HOME_CITY = "London"
HOME_AIRPORTS = ["LGW"]
EARLIEST_DEPARTURE = date(2026, 4, 3)
LATEST_RETURN = date(2026, 4, 14)
MIN_DAYS = 5
MAX_DAYS = 14
NUM_PEOPLE = 2

# ── Cache paths (separate from main run) ─────────────────────
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CACHE_DEALS = os.path.join(CACHE_DIR, "cache_gatwick_deals.json")
CACHE_ROUTES = os.path.join(CACHE_DIR, "cache_gatwick_routes.flag")
CACHE_ENRICHED = os.path.join(CACHE_DIR, "cache_gatwick_enriched.json")
OUTPUT_FILE = os.path.join(CACHE_DIR, "holiday_options_gatwick.xlsx")


def _save_cache(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _load_cache(path: str):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _clear_all_caches():
    for p in [CACHE_DEALS, CACHE_ROUTES, CACHE_ENRICHED]:
        if os.path.exists(p):
            os.remove(p)


def _to_spreadsheet_format(backend_result: dict, num_people: int) -> dict:
    """Convert backend enriched result to the format build_spreadsheet expects."""
    deal_info = backend_result["deal"]

    deal = {
        "pickup_city": deal_info["pickup_city"],
        "dropoff_city": deal_info["dropoff_city"],
        "depart_date": deal_info["pickup_date"],
        "deliver_date": deal_info["dropoff_date"],
        "drive_days": deal_info["drive_days"],
        "vehicle": deal_info.get("vehicle_type", ""),
        "rate_raw": "",
        "rate_gbp": deal_info.get("imoova_price_gbp", 0),
        "seats": deal_info.get("seats", 0),
        "deal_url": deal_info.get("imoova_url", ""),
    }

    out = backend_result.get("outbound_flight")
    ret = backend_result.get("return_flight")

    total = deal["rate_gbp"] / num_people
    if out:
        total += out["price_gbp"]
    if ret:
        total += ret["price_gbp"]

    outbound_uk = None
    return_uk = None

    return {
        "deal": deal,
        "outbound_flights": [out] if out else [],
        "return_flights": [ret] if ret else [],
        "outbound_uk_transport": outbound_uk,
        "return_uk_transport": return_uk,
        "cheapest_outbound": out,
        "cheapest_return": ret,
        "total_cost": round(total, 2),
        "is_complete": backend_result.get("is_complete", False),
        "warnings": backend_result.get("warnings", []),
    }


async def main():
    print("=" * 60)
    print("  Imoova Optimiser — London Gatwick (LGW) Only")
    print("=" * 60)
    print(f"  Home: {HOME_CITY} ({', '.join(HOME_AIRPORTS)})")
    print(f"  Dates: {EARLIEST_DEPARTURE} to {LATEST_RETURN}")
    print(f"  Drive days: {MIN_DAYS}-{MAX_DAYS}")
    print(f"  Travellers: {NUM_PEOPLE}")
    print()

    # Step 1: Scrape + Filter (cached)
    cached_deals = _load_cache(CACHE_DEALS)
    if cached_deals:
        filtered = cached_deals
        print(f"[1/4] Using cached deals ({len(filtered)} matches)")
    else:
        print("[1/4] Scraping Imoova deals...")
        raw_deals = await scrape_all_deals()
        print(f"  Found {len(raw_deals)} raw deals")

        filtered = filter_deals(
            raw_deals, EARLIEST_DEPARTURE, LATEST_RETURN, MIN_DAYS, MAX_DAYS
        )
        print(f"  {len(filtered)} match your constraints")
        _save_cache(CACHE_DEALS, filtered)

    print()

    if not filtered:
        print("  No deals match. Adjust your dates or duration range.")
        return

    for d in filtered[:5]:
        print(f"    {d['pickup_city']} -> {d['dropoff_city']} | "
              f"{d['depart_date']} | {d['drive_days']}d")
    if len(filtered) > 5:
        print(f"    ... and {len(filtered) - 5} more")
    print()

    # Step 2: Pre-search unique flight routes (cached)
    if os.path.exists(CACHE_ROUTES):
        print("[2/4] Route pre-search already done (cached)")
    else:
        print("[2/4] Pre-searching unique flight routes...")
        search_start = time.time()

        async def on_progress(searched, total):
            elapsed = time.time() - search_start
            if searched > 0:
                eta = (total - searched) * (elapsed / searched)
                print(f"\r  {searched}/{total} routes searched "
                      f"(~{eta:.0f}s remaining)    ", end="", flush=True)

        await presearch_unique_routes(
            filtered, HOME_CITY, HOME_AIRPORTS, EARLIEST_DEPARTURE, LATEST_RETURN, on_progress
        )
        _save_cache(CACHE_ROUTES, True)
        print()
    print()

    # Step 3: Enrich each deal with flight pairs (resumable)
    cached_partial = _load_cache(CACHE_ENRICHED)
    enriched = cached_partial if cached_partial else []
    start_idx = len(enriched)
    total = len(filtered)

    if start_idx >= total:
        print(f"[3/4] All {total} deals already enriched (cached)")
    else:
        if start_idx > 0:
            print(f"[3/4] Resuming flight pairs from deal {start_idx + 1}/{total}...")
        else:
            print("[3/4] Finding cheapest flight pairs...")

        for i, deal in enumerate(filtered[start_idx:], start_idx + 1):
            if i % 10 == 1 or i == total:
                print(f"  [{i}/{total}] {deal['pickup_city']} -> {deal['dropoff_city']}")

            try:
                result = await search_flights_for_deal(
                    deal, HOME_CITY, HOME_AIRPORTS,
                    EARLIEST_DEPARTURE, LATEST_RETURN,
                )
                enriched.append(_to_spreadsheet_format(result, NUM_PEOPLE))
            except Exception as e:
                print(f"    Error: {e}")
                enriched.append({
                    "deal": {
                        "pickup_city": deal.get("pickup_city", ""),
                        "dropoff_city": deal.get("dropoff_city", ""),
                        "depart_date": deal.get("depart_date", ""),
                        "deliver_date": deal.get("deliver_date", ""),
                        "drive_days": deal.get("drive_days", 0),
                        "vehicle": deal.get("vehicle", ""),
                        "rate_raw": deal.get("rate_raw", ""),
                        "rate_gbp": deal.get("rate_gbp", 0),
                        "seats": deal.get("seats", 0),
                        "deal_url": deal.get("deal_url", ""),
                    },
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

            if len(enriched) % 10 == 0:
                _save_cache(CACHE_ENRICHED, enriched)

        _save_cache(CACHE_ENRICHED, enriched)

    await close_browser()

    enriched.sort(key=lambda x: x["total_cost"])

    # Step 4: Build spreadsheet — override output path for Gatwick file
    print()
    print("[4/4] Building spreadsheet...")
    original_output = config.OUTPUT_PATH
    config.OUTPUT_PATH = OUTPUT_FILE
    path = build_spreadsheet(enriched, [])
    config.OUTPUT_PATH = original_output
    print(f"  Saved to: {path}")
    _clear_all_caches()
    print("  Cleared intermediate caches.")
    print()

    complete = [d for d in enriched if d["is_complete"]]
    print("=" * 60)
    print(f"  {len(complete)}/{len(filtered)} deals with complete pricing")
    print(f"  Per-person total (van hire split between {NUM_PEOPLE})")
    print("=" * 60)
    print()

    for i, item in enumerate(complete[:10], 1):
        d = item["deal"]
        out = item.get("cheapest_outbound")
        ret = item.get("cheapest_return")
        out_str = f"£{out['price_gbp']:.0f}" if out else "—"
        ret_str = f"£{ret['price_gbp']:.0f}" if ret else "—"
        print(f"  #{i:2d}  £{item['total_cost']:.2f}  "
              f"{d['pickup_city']} -> {d['dropoff_city']} "
              f"({d['drive_days']}d) "
              f"[out {out_str} + ret {ret_str} + van £{d['rate_gbp']/NUM_PEOPLE:.2f}]")

    print()
    print(f"  Full results: {path}")


if __name__ == "__main__":
    asyncio.run(main())
