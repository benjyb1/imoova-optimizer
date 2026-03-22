"""
Configuration constants for the Imoova Campervan Holiday Optimizer.
Airport mappings, date ranges, file paths, and rate limits.
"""

from __future__ import annotations
from datetime import date
import os

# ── Travel window ──────────────────────────────────────────────
TRAVEL_WINDOW_START = date(2026, 3, 28)
TRAVEL_WINDOW_END = date(2026, 4, 10)
MIN_DRIVE_DAYS = 5
MAX_DRIVE_DAYS = 10

# ── Currency conversion (rough, for Imoova rate parsing) ──────
EUR_TO_GBP = 0.86
USD_TO_GBP = 0.79
AUD_TO_GBP = 0.51

# ── London airports ───────────────────────────────────────────
LONDON_AIRPORTS = ["LHR", "LGW", "STN", "LTN", "SEN"]
# Budget carriers fly from these. Search these to keep query count down.
# STN = Ryanair hub, LGW = easyJet hub. LTN adds marginal value.
LONDON_PRIORITY_AIRPORTS = ["STN", "LGW"]

# ── City → IATA airport codes ────────────────────────────────
# Multi-airport cities list all relevant codes.
CITY_AIRPORTS: dict[str, list[str]] = {
    # UK
    "London": LONDON_AIRPORTS,
    "Manchester": ["MAN"],
    "Birmingham": ["BHX"],
    "Edinburgh": ["EDI"],
    "Glasgow": ["GLA"],
    "Bristol": ["BRS"],
    "Leeds": ["LBA"],
    "Liverpool": ["LPL"],
    "Newcastle": ["NCL"],
    "Southampton": ["SOU"],
    "Belfast": ["BFS", "BHD"],
    "Cardiff": ["CWL"],
    # France
    "Paris": ["CDG", "ORY"],
    "Lyon": ["LYS"],
    "Marseille": ["MRS"],
    "Nice": ["NCE"],
    "Bordeaux": ["BOD"],
    "Toulouse": ["TLS"],
    "Nantes": ["NTE"],
    "Strasbourg": ["SXB"],
    "Montpellier": ["MPL"],
    "Bastia": ["BIA"],
    # Spain
    "Barcelona": ["BCN"],
    "Madrid": ["MAD"],
    "Malaga": ["AGP"],
    "Seville": ["SVQ"],
    "Valencia": ["VLC"],
    "Alicante": ["ALC"],
    "Bilbao": ["BIO"],
    "Palma": ["PMI"],
    "Palma de Mallorca": ["PMI"],
    # Italy
    "Rome": ["FCO", "CIA"],
    "Milan": ["MXP", "LIN", "BGY"],
    "Venice": ["VCE", "TSF"],
    "Florence": ["FLR"],
    "Naples": ["NAP"],
    "Bologna": ["BLQ"],
    "Turin": ["TRN"],
    "Palermo": ["PMO"],
    "Catania": ["CTA"],
    "Bari": ["BRI"],
    "Pisa": ["PSA"],
    "Genoa": ["GOA"],
    "Olbia": ["OLB"],
    "Cagliari": ["CAG"],
    "Bergamo": ["BGY"],
    # Germany
    "Berlin": ["BER"],
    "Munich": ["MUC"],
    "Frankfurt": ["FRA", "HHN"],
    "Hamburg": ["HAM"],
    "Cologne": ["CGN"],
    "Dusseldorf": ["DUS"],
    "Stuttgart": ["STR"],
    "Hannover": ["HAJ"],
    "Nuremberg": ["NUE"],
    # Netherlands / Belgium / Luxembourg
    "Amsterdam": ["AMS"],
    "Brussels": ["BRU", "CRL"],
    "Eindhoven": ["EIN"],
    "Luxembourg": ["LUX"],
    # Scandinavia
    "Copenhagen": ["CPH"],
    "Stockholm": ["ARN"],
    "Oslo": ["OSL"],
    "Helsinki": ["HEL"],
    "Gothenburg": ["GOT"],
    "Malmo": ["MMX"],
    "Malmö": ["MMX"],
    # Central / Eastern Europe
    "Vienna": ["VIE"],
    "Prague": ["PRG"],
    "Budapest": ["BUD"],
    "Warsaw": ["WAW"],
    "Krakow": ["KRK"],
    "Bratislava": ["BTS"],
    "Zagreb": ["ZAG"],
    "Bucharest": ["OTP"],
    "Sofia": ["SOF"],
    "Ljubljana": ["LJU"],
    # Switzerland
    "Zurich": ["ZRH"],
    "Geneva": ["GVA"],
    "Basel": ["BSL"],
    # Portugal
    "Lisbon": ["LIS"],
    "Porto": ["OPO"],
    "Faro": ["FAO"],
    # Greece
    "Athens": ["ATH"],
    "Thessaloniki": ["SKG"],
    # Ireland
    "Dublin": ["DUB"],
    "Cork": ["ORK"],
    # Other
    "Reykjavik": ["KEF"],
    "Tallinn": ["TLL"],
    "Riga": ["RIX"],
    "Vilnius": ["VNO"],
    "Split": ["SPU"],
    "Dubrovnik": ["DBV"],
}

# ── UK cities (for domestic transport logic) ──────────────────
UK_CITIES: set[str] = {
    "London", "Manchester", "Birmingham", "Edinburgh", "Glasgow",
    "Bristol", "Leeds", "Liverpool", "Southampton", "Newcastle",
    "Belfast", "Cardiff",
}

# ── Train estimates: one-way to/from London in GBP ────────────
# Conservative advance-purchase prices. Flagged as estimates in output.
UK_TRAIN_ESTIMATES: dict[str, float] = {
    "Manchester": 25.0,
    "Birmingham": 15.0,
    "Edinburgh": 40.0,
    "Glasgow": 40.0,
    "Bristol": 20.0,
    "Leeds": 25.0,
    "Liverpool": 25.0,
    "Southampton": 15.0,
    "Newcastle": 30.0,
    "Cardiff": 25.0,
    "Belfast": 60.0,  # flight more likely cheaper
}

# ── City coordinates (lat, lon) for driving time estimates ────
# Approximate city-centre coordinates. Used to estimate straight-line
# distance, then multiplied by a road factor to get rough driving hours.
CITY_COORDS: dict[str, tuple[float, float]] = {
    # UK
    "London": (51.51, -0.13), "Manchester": (53.48, -2.24),
    "Birmingham": (52.49, -1.89), "Edinburgh": (55.95, -3.19),
    "Glasgow": (55.86, -4.25), "Bristol": (51.45, -2.58),
    "Leeds": (53.80, -1.55), "Liverpool": (53.41, -2.98),
    "Newcastle": (54.98, -1.61), "Southampton": (50.90, -1.40),
    "Belfast": (54.60, -5.93), "Cardiff": (51.48, -3.18),
    # France
    "Paris": (48.86, 2.35), "Lyon": (45.76, 4.83),
    "Marseille": (43.30, 5.37), "Nice": (43.71, 7.27),
    "Bordeaux": (44.84, -0.58), "Toulouse": (43.60, 1.44),
    "Nantes": (47.22, -1.55), "Strasbourg": (48.57, 7.75),
    "Montpellier": (43.61, 3.88), "Bastia": (42.70, 9.45),
    # Spain
    "Barcelona": (41.39, 2.17), "Madrid": (40.42, -3.70),
    "Malaga": (36.72, -4.42), "Seville": (37.39, -5.98),
    "Valencia": (39.47, -0.38), "Alicante": (38.35, -0.48),
    "Bilbao": (43.26, -2.93), "Palma": (39.57, 2.65),
    "Palma de Mallorca": (39.57, 2.65), "Tenerife": (28.47, -16.25),
    "A Coruña": (43.37, -8.40),
    # Italy
    "Rome": (41.90, 12.50), "Milan": (45.46, 9.19),
    "Venice": (45.44, 12.32), "Florence": (43.77, 11.25),
    "Naples": (40.85, 14.27), "Bologna": (44.49, 11.34),
    "Turin": (45.07, 7.69), "Palermo": (38.12, 13.36),
    "Catania": (37.50, 15.09), "Bari": (41.12, 16.87),
    "Pisa": (43.72, 10.40), "Genoa": (44.41, 8.93),
    "Olbia": (40.92, 9.50), "Cagliari": (39.22, 9.12),
    "Bergamo": (45.70, 9.67),
    # Germany
    "Berlin": (52.52, 13.41), "Munich": (48.14, 11.58),
    "Frankfurt": (50.11, 8.68), "Hamburg": (53.55, 9.99),
    "Cologne": (50.94, 6.96), "Dusseldorf": (51.23, 6.77),
    "Stuttgart": (48.78, 9.18), "Hannover": (52.37, 9.74),
    "Nuremberg": (49.45, 11.08),
    # Benelux
    "Amsterdam": (52.37, 4.90), "Brussels": (50.85, 4.35),
    "Eindhoven": (51.44, 5.47), "Luxembourg": (49.61, 6.13),
    # Scandinavia
    "Copenhagen": (55.68, 12.57), "Stockholm": (59.33, 18.07),
    "Oslo": (59.91, 10.75), "Helsinki": (60.17, 24.94),
    "Gothenburg": (57.71, 11.97), "Malmö": (55.61, 13.00),
    "Malmo": (55.61, 13.00), "Bergen": (60.39, 5.32),
    "Trondheim": (63.43, 10.40),
    # Central/Eastern Europe
    "Vienna": (48.21, 16.37), "Prague": (50.08, 14.44),
    "Budapest": (47.50, 19.04), "Warsaw": (52.23, 21.01),
    "Krakow": (50.06, 19.94), "Bratislava": (48.15, 17.11),
    "Zagreb": (45.81, 15.98), "Bucharest": (44.43, 26.10),
    "Sofia": (42.70, 23.32), "Ljubljana": (46.06, 14.51),
    # Switzerland
    "Zurich": (47.38, 8.54), "Geneva": (46.20, 6.14),
    "Basel": (47.56, 7.59),
    # Portugal
    "Lisbon": (38.72, -9.14), "Porto": (41.15, -8.61),
    "Faro": (37.02, -7.94),
    # Greece
    "Athens": (37.98, 23.73), "Thessaloniki": (40.64, 22.94),
    # Ireland
    "Dublin": (53.35, -6.26), "Cork": (51.90, -8.47),
    # Other
    "Reykjavik": (64.15, -21.94), "Tallinn": (59.44, 24.75),
    "Riga": (56.95, 24.11), "Vilnius": (54.69, 25.28),
    "Split": (43.51, 16.44), "Dubrovnik": (42.65, 18.09),
    # Extra Imoova cities not in CITY_AIRPORTS
    "Paris Orly": (48.73, 2.37),
}

# Average speed in km/h on European roads (accounts for motorways, towns, breaks)
_AVG_SPEED_KMH = 80
# Road winding factor: roads are ~1.3x longer than straight-line distance
_ROAD_FACTOR = 1.3


def estimate_driving_hours(city_a: str, city_b: str) -> float | None:
    """
    Estimate driving hours between two cities using straight-line distance
    with a road factor. Returns None if either city has no coordinates.
    """
    import math

    coords_a = _get_city_coords(city_a)
    coords_b = _get_city_coords(city_b)
    if coords_a is None or coords_b is None:
        return None

    lat1, lon1 = math.radians(coords_a[0]), math.radians(coords_a[1])
    lat2, lon2 = math.radians(coords_b[0]), math.radians(coords_b[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    km = 6371 * c  # Earth radius in km

    road_km = km * _ROAD_FACTOR
    hours = road_km / _AVG_SPEED_KMH
    return round(hours, 1)


def _get_city_coords(city_name: str) -> tuple[float, float] | None:
    """Look up coordinates for a city, trying exact then substring match."""
    if not city_name:
        return None
    cleaned = city_name.strip()
    # Exact match
    for key, coords in CITY_COORDS.items():
        if key.lower() == cleaned.lower():
            return coords
    # Substring match
    for key, coords in CITY_COORDS.items():
        if key.lower() in cleaned.lower() or cleaned.lower() in key.lower():
            return coords
    return None


# ── Imoova ────────────────────────────────────────────────────
IMOOVA_TABLE_URL = "https://www.imoova.com/en/relocations/table/europe"
IMOOVA_BASE_URL = "https://www.imoova.com"

# ── Rate limiting & caching ───────────────────────────────────
# Delay between Google Flights searches. 1.5s is enough with persistent browser.
FAST_FLIGHTS_DELAY_SECONDS = 1.5
API_DELAY_SECONDS = 1.5
FLIGHT_CACHE_TTL_HOURS = 9999
MAX_CONSECUTIVE_FAILURES = 5

# ── File paths ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FLIGHT_CACHE_DIR = os.path.join(DATA_DIR, "flight_cache")
IMOOVA_CACHE_PATH = os.path.join(DATA_DIR, "imoova_deals.json")
API_LOG_PATH = os.path.join(DATA_DIR, "api_log.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "output", "holiday_options.xlsx")


def get_airports_for_city(city_name: str) -> list[str] | None:
    """
    Look up IATA airport codes for a city name.
    Tries exact match (case-insensitive), then substring match.
    Returns None if no match found.
    """
    if not city_name:
        return None

    cleaned = city_name.strip()

    # Exact match (case-insensitive)
    for key, codes in CITY_AIRPORTS.items():
        if key.lower() == cleaned.lower():
            return codes

    # Substring match: "Barcelona (Spain)" -> "Barcelona"
    for key, codes in CITY_AIRPORTS.items():
        if key.lower() in cleaned.lower() or cleaned.lower() in key.lower():
            return codes

    return None


def is_uk_city(city_name: str) -> bool:
    """Check if a city is in the UK (case-insensitive)."""
    if not city_name:
        return False
    cleaned = city_name.strip()
    return any(uk.lower() == cleaned.lower() for uk in UK_CITIES)


def is_london(city_name: str) -> bool:
    """Check if a city name refers to London."""
    if not city_name:
        return False
    return "london" in city_name.strip().lower()
