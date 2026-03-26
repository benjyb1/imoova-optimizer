"""
Run the Imoova optimizer locally using the backend modules.
Saves results to an Excel spreadsheet.

Usage: python run_local.py
"""
import asyncio
import os
import sys
import time

# Ensure root dir is first on path so 'import config' finds root config.py
# (not backend/config.py which is missing OUTPUT_PATH etc.)
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)
# Remove backend/ from path if present (would shadow root config)
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
HOME_AIRPORTS = config.LONDON_PRIORITY_AIRPORTS
EARLIEST_DEPARTURE = date(2026, 4, 3)
LATEST_RETURN = date(2026, 4, 14)
MIN_DAYS = 5
MAX_DAYS = 14
NUM_PEOPLE = 2


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

    # Per-person total: each flight is per person, van hire split
    total = deal["rate_gbp"] / num_people
    if out:
        total += out["price_gbp"]
    if ret:
        total += ret["price_gbp"]

    # UK transport
    outbound_uk = None
    return_uk = None
    if backend_result.get("outbound_is_home"):
        pass  # no transport needed
    if backend_result.get("return_is_home"):
        pass

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
    print("  Imoova Campervan Holiday Optimiser (Local)")
    print("=" * 60)
    print(f"  Home: {HOME_CITY}")
    print(f"  Dates: {EARLIEST_DEPARTURE} to {LATEST_RETURN}")
    print(f"  Drive days: {MIN_DAYS}-{MAX_DAYS}")
    print(f"  Travellers: {NUM_PEOPLE}")
    print()

    # Step 1: Scrape
    print("[1/4] Scraping Imoova deals...")
    raw_deals = await scrape_all_deals()
    print(f"  Found {len(raw_deals)} raw deals")

    # Step 2: Filter
    filtered = filter_deals(
        raw_deals, EARLIEST_DEPARTURE, LATEST_RETURN, MIN_DAYS, MAX_DAYS
    )
    print(f"  {len(filtered)} match your constraints")
    print()

    if not filtered:
        print("  No deals match. Adjust your dates or duration range.")
        return

    # Preview
    for d in filtered[:5]:
        print(f"    {d['pickup_city']} -> {d['dropoff_city']} | "
              f"{d['depart_date']} | {d['drive_days']}d")
    if len(filtered) > 5:
        print(f"    ... and {len(filtered) - 5} more")
    print()

    # Step 3: Pre-search unique flight routes
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
    print()
    print()

    # Step 4: Enrich each deal with flight pairs
    print("[3/4] Finding cheapest flight pairs...")
    enriched = []
    total = len(filtered)

    for i, deal in enumerate(filtered, 1):
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

    await close_browser()

    # Sort by total cost
    enriched.sort(key=lambda x: x["total_cost"])

    # Step 5: Build spreadsheet
    print()
    print("[4/4] Building spreadsheet...")
    path = build_spreadsheet(enriched, [])
    print(f"  Saved to: {path}")
    print()

    # Summary
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
