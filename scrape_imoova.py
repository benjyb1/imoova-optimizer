"""
Scrape Imoova European relocation deals from the table view.
Uses Playwright to handle dynamic loading ("Load more" pagination).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

import config


@dataclass
class ImoovaDeal:
    ref: str
    pickup_city: str
    dropoff_city: str
    depart_date: str          # ISO format YYYY-MM-DD
    deliver_date: str         # ISO format YYYY-MM-DD
    drive_days: int
    vehicle: str
    rate_raw: str             # original string e.g. "FREE", "€1/day"
    rate_gbp: float           # normalised numeric cost for the whole trip
    seats: int
    fuel: str
    ferry: str
    deal_url: str


class ScrapingError(Exception):
    pass


def parse_date(text: str) -> date | None:
    """Parse date strings like '28 Mar 2026', '28 Mar', '2026-03-28'."""
    text = text.strip()
    formats = ["%d %b %Y", "%d %b %y", "%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # If no year given, try adding current travel year
    for fmt in ["%d %b", "%d %B"]:
        try:
            parsed = datetime.strptime(text, fmt).date()
            return parsed.replace(year=2026)
        except ValueError:
            continue

    return None


def parse_days(text: str) -> int:
    """
    Parse days string like '4 + 1 nights', '5', '7+2'.
    Returns only the included driving days (first number).
    The '+N' is optional paid buffer days — we never include those.
    """
    text = text.strip()
    numbers = re.findall(r"\d+", text)
    if not numbers:
        return 0
    return int(numbers[0])


def parse_drive_days_only(text: str) -> int:
    """Return just the driving days portion (first number)."""
    text = text.strip()
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 0


def parse_rate_to_gbp(rate_str: str, total_days: int) -> float:
    """
    Convert rate strings to total trip cost in GBP.
    Examples: 'FREE', '$0', '€1/day', '$1/day', '€50', 'A$250'
    """
    text = rate_str.strip().upper()

    if text in ("FREE", "$0", "€0", "£0", "0"):
        return 0.0

    # Check for per-day rates
    per_day = "/DAY" in text or "/NIGHT" in text or "/24" in text

    # Extract numeric value
    numeric = re.findall(r"[\d.]+", text)
    if not numeric:
        return 0.0
    amount = float(numeric[0])

    # Determine currency and convert
    if "£" in rate_str:
        gbp = amount
    elif "€" in rate_str or "EUR" in text:
        gbp = amount * config.EUR_TO_GBP
    elif "A$" in rate_str or "AUD" in text:
        gbp = amount * config.AUD_TO_GBP
    elif "$" in rate_str or "USD" in text:
        gbp = amount * config.USD_TO_GBP
    else:
        # Default to EUR for European deals
        gbp = amount * config.EUR_TO_GBP

    if per_day and total_days > 0:
        gbp *= total_days

    return round(gbp, 2)


def parse_seats(text: str) -> int:
    """Parse seats count from text like '2', '4-5', etc."""
    numbers = re.findall(r"\d+", text.strip())
    return int(numbers[0]) if numbers else 0


async def scrape_all_deals() -> list[dict]:
    """
    Launch Playwright, load the Imoova table view, click 'Load more'
    until all deals are loaded, then parse every table row.
    """
    print("  Launching browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        # Load the table view with retries
        for attempt in range(3):
            try:
                print(f"  Loading Imoova table view (attempt {attempt + 1})...")
                await page.goto(config.IMOOVA_TABLE_URL, wait_until="networkidle", timeout=30000)
                # Wait for the table to appear
                await page.wait_for_selector("table", timeout=15000)
                break
            except PlaywrightTimeout:
                if attempt == 2:
                    raise ScrapingError(
                        f"Could not load Imoova table at {config.IMOOVA_TABLE_URL} after 3 attempts"
                    )
                print(f"  Timeout, retrying in 5s...")
                await asyncio.sleep(5)

        # Click "Load more" until all deals are loaded
        load_more_clicks = 0
        prev_row_count = 0
        while True:
            # Count current rows
            rows = await page.query_selector_all("table tbody tr")
            current_count = len(rows)

            if current_count == prev_row_count and load_more_clicks > 0:
                # No new rows after last click, we're done
                break

            prev_row_count = current_count

            # Look for a "Load more" or "Show more" button
            load_more = await page.query_selector(
                "button:has-text('Load more'), button:has-text('Show more'), "
                "a:has-text('Load more'), a:has-text('Show more'), "
                "[data-testid*='load-more'], [class*='load-more']"
            )

            if not load_more:
                # Also try looking for any button at the bottom of the table area
                load_more = await page.query_selector(
                    "table ~ button, table ~ div button"
                )

            if not load_more:
                break

            try:
                await load_more.scroll_into_view_if_needed()
                await load_more.click()
                load_more_clicks += 1
                if load_more_clicks % 5 == 0:
                    print(f"  Loaded {current_count} deals so far...")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  Load more click failed: {e}")
                break

        # Parse the table
        print(f"  Parsing table ({prev_row_count} rows)...")
        deals = await parse_table(page)
        await browser.close()
        return deals


async def parse_table(page: Page) -> list[dict]:
    """Parse all rows from the HTML table."""
    # Get column headers
    headers = await page.eval_on_selector_all(
        "table thead th, table thead td",
        "els => els.map(e => e.textContent.trim().toLowerCase())"
    )

    if not headers:
        # Try alternative: first row might be headers
        headers = await page.eval_on_selector_all(
            "table tr:first-child th, table tr:first-child td",
            "els => els.map(e => e.textContent.trim().toLowerCase())"
        )

    print(f"  Table columns: {headers}")

    # Map column indices by exact header name match
    # Known headers: ref, from, to, depart, deliver, vehicle, rate, days, seats, fuel, ferry
    header_to_key = {
        "ref": "ref",
        "from": "from",
        "to": "to",
        "depart": "depart",
        "deliver": "deliver",
        "vehicle": "vehicle",
        "rate": "rate",
        "price": "rate",
        "cost": "rate",
        "days": "days",
        "seats": "seats",
        "fuel": "fuel",
        "ferry": "ferry",
    }

    col_map = {}
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        if h_lower in header_to_key:
            col_map[header_to_key[h_lower]] = i

    # Fallback: positional mapping if header detection missed columns
    if len(col_map) < 6 and len(headers) >= 11:
        col_map = {
            "ref": 0, "from": 1, "to": 2, "depart": 3, "deliver": 4,
            "vehicle": 5, "rate": 6, "days": 7, "seats": 8, "fuel": 9, "ferry": 10,
        }

    print(f"  Column mapping: {col_map}")

    # Get all data rows
    rows_data = await page.eval_on_selector_all(
        "table tbody tr",
        """rows => rows.map(row => {
            const cells = row.querySelectorAll('td');
            const data = Array.from(cells).map(c => c.textContent.trim());
            // Also grab the first link href for the deal URL
            const link = row.querySelector('a');
            const href = link ? link.getAttribute('href') : '';
            return { cells: data, href: href };
        })"""
    )

    deals = []
    for row in rows_data:
        cells = row.get("cells", [])
        href = row.get("href", "")

        if len(cells) < 6:
            continue

        try:
            ref = cells[col_map.get("ref", 0)] if "ref" in col_map else ""
            pickup = cells[col_map.get("from", 1)] if "from" in col_map else ""
            dropoff = cells[col_map.get("to", 2)] if "to" in col_map else ""
            depart_str = cells[col_map.get("depart", 3)] if "depart" in col_map else ""
            deliver_str = cells[col_map.get("deliver", 4)] if "deliver" in col_map else ""
            vehicle = cells[col_map.get("vehicle", 5)] if "vehicle" in col_map else ""
            rate_raw = cells[col_map.get("rate", 6)] if "rate" in col_map else "FREE"
            days_str = cells[col_map.get("days", 7)] if "days" in col_map else "0"
            seats_str = cells[col_map.get("seats", 8)] if "seats" in col_map else "0"
            fuel = cells[col_map.get("fuel", 9)] if "fuel" in col_map else ""
            ferry = cells[col_map.get("ferry", 10)] if "ferry" in col_map else ""

            depart_date = parse_date(depart_str)
            deliver_date = parse_date(deliver_str)
            total_days = parse_days(days_str)
            drive_days = parse_drive_days_only(days_str)

            if not depart_date or not deliver_date:
                continue

            # Build deal URL
            deal_url = href
            if deal_url and not deal_url.startswith("http"):
                deal_url = config.IMOOVA_BASE_URL + deal_url

            deal = ImoovaDeal(
                ref=ref,
                pickup_city=pickup,
                dropoff_city=dropoff,
                depart_date=depart_date.isoformat(),
                deliver_date=deliver_date.isoformat(),
                drive_days=total_days if total_days > 0 else (deliver_date - depart_date).days,
                vehicle=vehicle,
                rate_raw=rate_raw,
                rate_gbp=parse_rate_to_gbp(rate_raw, total_days if total_days > 0 else (deliver_date - depart_date).days),
                seats=parse_seats(seats_str),
                fuel=fuel,
                ferry=ferry,
                deal_url=deal_url,
            )
            deals.append(asdict(deal))

        except (IndexError, ValueError) as e:
            print(f"  Warning: skipping unparseable row: {e}")
            continue

    return deals


def filter_deals(raw_deals: list[dict]) -> list[dict]:
    """
    Filter deals to match our travel constraints:

    Hard deadline: must be home by TRAVEL_WINDOW_END.
    Earliest departure: TRAVEL_WINDOW_START.

    You fly out the day before or day of pickup, and fly home the day
    of or day after delivery. So the full trip span from the user's
    perspective is roughly (pickup_date - 1) to (deliver_date + 1).

    Max trip length is dynamic: if you leave later, you have fewer
    days before the deadline. Min trip is still MIN_DRIVE_DAYS.

    Also filters out:
    - Both cities in the UK
    - Same-country trips
    """
    filtered = []
    for deal in raw_deals:
        depart = date.fromisoformat(deal["depart_date"])
        deliver = date.fromisoformat(deal["deliver_date"])
        days = deal["drive_days"]

        # Can't pick up before we can leave
        if depart < config.TRAVEL_WINDOW_START:
            continue

        # Must be home by deadline. You fly back day of or day after
        # delivery, so deliver + 1 must be <= TRAVEL_WINDOW_END.
        if deliver + timedelta(days=1) > config.TRAVEL_WINDOW_END:
            continue

        # Min trip length still applies
        if days < config.MIN_DRIVE_DAYS:
            continue

        # At least one end must be outside the UK
        pickup_uk = config.is_uk_city(deal["pickup_city"])
        dropoff_uk = config.is_uk_city(deal["dropoff_city"])
        if pickup_uk and dropoff_uk:
            continue

        # Skip Germany-to-Germany trips (short boring hops)
        pickup_country = config.CITY_COUNTRIES.get(deal["pickup_city"], "")
        dropoff_country = config.CITY_COUNTRIES.get(deal["dropoff_city"], "")
        if pickup_country == dropoff_country and pickup_country == "Germany":
            continue

        filtered.append(deal)

    return filtered


def is_cache_fresh() -> bool:
    """Check if the Imoova cache exists and is less than 6 hours old."""
    if not os.path.exists(config.IMOOVA_CACHE_PATH):
        return False
    age_hours = (time.time() - os.path.getmtime(config.IMOOVA_CACHE_PATH)) / 3600
    return age_hours < config.FLIGHT_CACHE_TTL_HOURS


def run_scraper() -> dict:
    """
    Main entry point. Scrape deals, filter, cache, and return.
    Uses cached data if fresh enough.
    """
    if is_cache_fresh():
        print("  Using cached Imoova data...")
        with open(config.IMOOVA_CACHE_PATH) as f:
            cached = json.load(f)
        filtered = filter_deals(cached["raw"])
        print(f"  Cache has {len(cached['raw'])} raw deals, {len(filtered)} match our window.")
        return {"raw": cached["raw"], "filtered": filtered}

    raw_deals = asyncio.run(scrape_all_deals())
    filtered = filter_deals(raw_deals)

    # Save cache
    os.makedirs(os.path.dirname(config.IMOOVA_CACHE_PATH), exist_ok=True)
    with open(config.IMOOVA_CACHE_PATH, "w") as f:
        json.dump({"raw": raw_deals, "scraped_at": datetime.now().isoformat()}, f, indent=2)

    return {"raw": raw_deals, "filtered": filtered}


if __name__ == "__main__":
    print("=== Imoova Scraper (standalone test) ===\n")
    result = run_scraper()
    print(f"\nTotal deals scraped: {len(result['raw'])}")
    print(f"Deals matching travel window: {len(result['filtered'])}")
    if result["filtered"]:
        print("\nFirst 3 matching deals:")
        for d in result["filtered"][:3]:
            print(f"  {d['pickup_city']} -> {d['dropoff_city']} | "
                  f"{d['depart_date']} | {d['drive_days']} days | "
                  f"{d['rate_raw']} (£{d['rate_gbp']:.2f})")
