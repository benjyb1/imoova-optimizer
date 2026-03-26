"""
Scrape Imoova European relocation deals from the table view.
Uses Playwright to handle dynamic loading ("Load more" pagination).

Adapted from the original scrape_imoova.py for the web backend.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

import config

logger = logging.getLogger(__name__)


class ScrapingError(Exception):
    pass


def parse_date(text: str) -> Optional[date]:
    """Parse date strings like '28 Mar 2026', '28 Mar', '2026-03-28'."""
    text = text.strip()
    formats = ["%d %b %Y", "%d %b %y", "%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # If no year given, try adding current year
    current_year = date.today().year
    for fmt in ["%d %b", "%d %B"]:
        try:
            parsed = datetime.strptime(text, fmt).date()
            return parsed.replace(year=current_year)
        except ValueError:
            continue

    return None


def parse_days(text: str) -> int:
    """
    Parse days string like '4 + 1 nights', '5', '7+2'.
    Returns only the included driving days (first number).
    The '+N' is optional paid buffer days, not free.
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
    Examples: 'FREE', '$0', '\u20ac1/day', '$1/day', '\u20ac50', 'A$250'
    """
    text = rate_str.strip().upper()

    if text in ("FREE", "$0", "\u20ac0", "\u00a30", "0"):
        return 0.0

    per_day = "/DAY" in text or "/NIGHT" in text or "/24" in text

    numeric = re.findall(r"[\d.]+", text)
    if not numeric:
        return 0.0
    amount = float(numeric[0])

    if "\u00a3" in rate_str:
        gbp = amount
    elif "\u20ac" in rate_str or "EUR" in text:
        gbp = amount * config.EUR_TO_GBP
    elif "A$" in rate_str or "AUD" in text:
        gbp = amount * config.AUD_TO_GBP
    elif "$" in rate_str or "USD" in text:
        gbp = amount * config.USD_TO_GBP
    else:
        gbp = amount * config.EUR_TO_GBP

    if per_day and total_days > 0:
        gbp *= total_days

    return round(gbp, 2)


def parse_seats(text: str) -> int:
    """Parse seats count from text like '2', '4-5', etc."""
    numbers = re.findall(r"\d+", text.strip())
    return int(numbers[0]) if numbers else 0


async def scrape_all_deals() -> List[Dict[str, Any]]:
    """
    Launch Playwright, load the Imoova table view, click 'Load more'
    until all deals are loaded, then parse every table row.
    """
    logger.info("Launching browser for Imoova scrape...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36"
            ),
        )
        page = await context.new_page()

        for attempt in range(3):
            try:
                logger.info("Loading Imoova table (attempt %d)...", attempt + 1)
                await page.goto(
                    config.IMOOVA_TABLE_URL,
                    wait_until="networkidle",
                    timeout=30000,
                )
                await page.wait_for_selector("table", timeout=15000)
                break
            except PlaywrightTimeout:
                if attempt == 2:
                    raise ScrapingError(
                        f"Could not load Imoova table at {config.IMOOVA_TABLE_URL} "
                        "after 3 attempts"
                    )
                logger.warning("Timeout, retrying in 5s...")
                await asyncio.sleep(5)

        # Click "Load more" until all deals are loaded
        load_more_clicks = 0
        prev_row_count = 0
        while True:
            rows = await page.query_selector_all("table tbody tr")
            current_count = len(rows)

            if current_count == prev_row_count and load_more_clicks > 0:
                break

            prev_row_count = current_count

            load_more = await page.query_selector(
                "button:has-text('Load more'), button:has-text('Show more'), "
                "a:has-text('Load more'), a:has-text('Show more'), "
                "[data-testid*='load-more'], [class*='load-more']"
            )

            if not load_more:
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
                    logger.info("Loaded %d deals so far...", current_count)
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.warning("Load more click failed: %s", e)
                break

        logger.info("Parsing table (%d rows)...", prev_row_count)
        deals = await _parse_table(page)
        await browser.close()
        return deals


async def _parse_table(page: Page) -> List[Dict[str, Any]]:
    """Parse all rows from the HTML table."""
    headers = await page.eval_on_selector_all(
        "table thead th, table thead td",
        "els => els.map(e => e.textContent.trim().toLowerCase())",
    )

    if not headers:
        headers = await page.eval_on_selector_all(
            "table tr:first-child th, table tr:first-child td",
            "els => els.map(e => e.textContent.trim().toLowerCase())",
        )

    logger.info("Table columns: %s", headers)

    header_to_key = {
        "ref": "ref", "from": "from", "to": "to",
        "depart": "depart", "deliver": "deliver",
        "vehicle": "vehicle", "rate": "rate", "price": "rate", "cost": "rate",
        "days": "days", "seats": "seats", "fuel": "fuel", "ferry": "ferry",
    }

    col_map: Dict[str, int] = {}
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        if h_lower in header_to_key:
            col_map[header_to_key[h_lower]] = i

    if len(col_map) < 6 and len(headers) >= 11:
        col_map = {
            "ref": 0, "from": 1, "to": 2, "depart": 3, "deliver": 4,
            "vehicle": 5, "rate": 6, "days": 7, "seats": 8,
            "fuel": 9, "ferry": 10,
        }

    rows_data = await page.eval_on_selector_all(
        "table tbody tr",
        """rows => rows.map(row => {
            const cells = row.querySelectorAll('td');
            const data = Array.from(cells).map(c => c.textContent.trim());
            const link = row.querySelector('a');
            const href = link ? link.getAttribute('href') : '';
            return { cells: data, href: href };
        })""",
    )

    deals: List[Dict[str, Any]] = []
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

            if not depart_date or not deliver_date:
                continue

            deal_url = href
            if deal_url and not deal_url.startswith("http"):
                deal_url = config.IMOOVA_BASE_URL + deal_url

            if total_days <= 0:
                total_days = (deliver_date - depart_date).days

            deal = {
                "ref": ref,
                "pickup_city": pickup,
                "dropoff_city": dropoff,
                "depart_date": depart_date.isoformat(),
                "deliver_date": deliver_date.isoformat(),
                "drive_days": total_days,
                "vehicle": vehicle,
                "rate_raw": rate_raw,
                "rate_gbp": parse_rate_to_gbp(rate_raw, total_days),
                "seats": parse_seats(seats_str),
                "fuel": fuel,
                "ferry": ferry,
                "deal_url": deal_url,
            }
            deals.append(deal)

        except (IndexError, ValueError) as e:
            logger.warning("Skipping unparseable row: %s", e)
            continue

    return deals


def filter_deals(
    raw_deals: List[Dict[str, Any]],
    earliest_departure: date,
    latest_return: date,
    min_days: int = 3,
    max_days: int = 10,
    min_seats: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Filter deals to match user's travel constraints.
    """
    filtered: List[Dict[str, Any]] = []
    for deal in raw_deals:
        days = deal["drive_days"]
        if days < min_days or days > max_days:
            continue

        # Skip deals with empty/invalid dates
        if not deal.get("depart_date") or not deal.get("deliver_date"):
            continue
        try:
            depart = date.fromisoformat(deal["depart_date"])
            deliver = date.fromisoformat(deal["deliver_date"])
        except (ValueError, TypeError):
            continue

        # Calculate the valid pickup window for this deal, constrained by
        # user's availability. Pickup can't be before depart or before the
        # user is free; dropoff (pickup + drive_days) can't exceed deliver
        # or latest_return.
        window_start = max(depart, earliest_departure)
        window_end = min(
            deliver - timedelta(days=days),
            latest_return - timedelta(days=days),
        )
        if window_start > window_end:
            continue

        if min_seats is not None and deal["seats"] < min_seats:
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
