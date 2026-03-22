"""
Imoova Campervan Holiday Optimizer
===================================
Finds the cheapest campervan holidays by combining Imoova relocation deals
with real flight prices from Google Flights (via fast-flights).

Usage: python main.py
"""

from __future__ import annotations

import sys
import json
import os

from scrape_imoova import run_scraper
from search_flights import search_all_deals, get_api_log, close_browser
from build_spreadsheet import build_spreadsheet
import config


def main():
    print("=" * 60)
    print("  Imoova Campervan Holiday Optimizer")
    print("=" * 60)
    print()
    print(f"  Travel window: {config.TRAVEL_WINDOW_START} to {config.TRAVEL_WINDOW_END}")
    print(f"  Drive days: {config.MIN_DRIVE_DAYS}-{config.MAX_DRIVE_DAYS}")
    print(f"  Home base: London (STN, LGW, LTN, LHR, SEN)")
    print()

    # ── Step 1: Scrape Imoova ─────────────────────────────────
    print("[1/4] Scraping Imoova deals...")
    try:
        imoova_data = run_scraper()
    except Exception as e:
        print(f"\n  ERROR: Failed to scrape Imoova: {e}")
        print("  Check your internet connection and try again.")
        sys.exit(1)

    raw_count = len(imoova_data["raw"])
    filtered_count = len(imoova_data["filtered"])
    print(f"  Found {raw_count} total European deals.")
    print(f"  {filtered_count} match our travel window and constraints.")
    print()

    if filtered_count == 0:
        print("  No deals match. Try widening your travel window in config.py.")
        sys.exit(0)

    # Show a preview of deals
    print("  Sample deals:")
    for d in imoova_data["filtered"][:5]:
        print(f"    {d['pickup_city']} -> {d['dropoff_city']} | "
              f"{d['depart_date']} | {d['drive_days']}d | "
              f"{d['rate_raw']} (£{d['rate_gbp']:.2f})")
    if filtered_count > 5:
        print(f"    ... and {filtered_count - 5} more")
    print()

    # ── Step 2: Search flights ────────────────────────────────
    print(f"[2/4] Searching flights for {filtered_count} deals...")
    print(f"  (This will take ~{filtered_count * 0.5:.0f}-{filtered_count * 2:.0f} minutes "
          f"with rate limiting)")
    print()

    enriched_deals = search_all_deals(imoova_data["filtered"])
    close_browser()  # Clean up persistent Playwright browser
    complete_count = sum(1 for d in enriched_deals if d["is_complete"])
    print()
    print(f"  Flight search complete.")
    print(f"  {complete_count}/{filtered_count} deals have complete flight pricing.")
    print()

    # ── Step 3: Build spreadsheet ─────────────────────────────
    print("[3/4] Building spreadsheet...")
    api_log = get_api_log()
    output_path = build_spreadsheet(enriched_deals, api_log)
    print(f"  Saved to: {output_path}")
    print()

    # ── Step 4: Terminal summary ──────────────────────────────
    print("[4/4] Results summary")
    print()

    # Filter to complete deals only for the top list
    complete_deals = [d for d in enriched_deals if d["is_complete"]]

    if not complete_deals:
        print("  No complete options found (all missing flight data).")
        print("  Check the spreadsheet for partial results and warnings.")
        print()
    else:
        top_n = min(5, len(complete_deals))
        print("=" * 60)
        print(f"  TOP {top_n} CHEAPEST COMPLETE HOLIDAY OPTIONS")
        print("=" * 60)
        print()

        for i, item in enumerate(complete_deals[:top_n], 1):
            _print_option(i, item)

    # Stats
    print("=" * 60)
    print(f"  Spreadsheet: {output_path}")
    print(f"  Total deals searched: {filtered_count}")
    print(f"  Complete options: {complete_count}")
    print(f"  API calls made: {len(api_log)}")
    print("=" * 60)


def _print_option(rank: int, item: dict):
    """Pretty-print a single holiday option."""
    deal = item["deal"]
    ob = item.get("cheapest_outbound")
    ret = item.get("cheapest_return")
    ob_uk = item.get("outbound_uk_transport")
    ret_uk = item.get("return_uk_transport")

    print(f"  #{rank}  TOTAL: £{item['total_cost']:.2f}")
    print(f"      Campervan: {deal['pickup_city']} -> {deal['dropoff_city']} | "
          f"{deal['drive_days']} days | {deal['depart_date']} to {deal['deliver_date']}")
    print(f"      Vehicle: {deal['vehicle']} | Imoova cost: £{deal['rate_gbp']:.2f} "
          f"({deal['rate_raw']})")

    if ob:
        print(f"      Outbound: {ob['airline']} | {ob['search_date']} | "
              f"{ob['departure_airport']}->{ob['arrival_airport']} "
              f"{ob['departure_time']}->{ob['arrival_time']} | "
              f"£{ob['price_gbp']:.2f}")
    elif ob_uk:
        print(f"      Outbound: {ob_uk['details']}")

    if ret:
        print(f"      Return:   {ret['airline']} | {ret['search_date']} | "
              f"{ret['departure_airport']}->{ret['arrival_airport']} "
              f"{ret['departure_time']}->{ret['arrival_time']} | "
              f"£{ret['price_gbp']:.2f}")
    elif ret_uk:
        print(f"      Return:   {ret_uk['details']}")

    if item.get("warnings"):
        for w in item["warnings"]:
            print(f"      !! {w}")

    print()


if __name__ == "__main__":
    main()
