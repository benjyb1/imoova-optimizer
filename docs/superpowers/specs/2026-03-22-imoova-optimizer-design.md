# Imoova Campervan Holiday Optimiser — Design Spec

## Goal

Build a Python CLI tool that finds the cheapest campervan holidays by combining Imoova relocation deals in Europe with real, bookable flights. Output a ranked spreadsheet with exact flight details so every option can be booked immediately.

## Constraints

- **Home base:** London, UK (LHR, LGW, STN, LTN, SEN)
- **Travel window:** Depart from 28 March 2026 onwards, back in London by 10 April 2026
- **Trip duration:** 5–10 drive days
- **Geography:** At least one end of the relocation must be outside the UK
- **Ranking:** Total cost ascending (Imoova price + outbound flight + return flight + UK transport if applicable)

## Architecture

Sequential pipeline orchestrated by `main.py`:

```
1. scrape_imoova.py  →  data/imoova_deals.json
2. search_flights.py →  data/flight_cache/*.json
3. uk_transport.py   →  domestic flights + train estimates
4. build_spreadsheet.py → output/holiday_options.xlsx
5. Terminal summary (top 5 to stdout)
```

### Project Structure

```
imoova-optimizer/
├── .env.example
├── .env                      # API keys (gitignored)
├── main.py                   # Orchestrator
├── scrape_imoova.py          # Imoova deal extraction
├── search_flights.py         # Flight price search via SerpAPI / Searchapi.io
├── uk_transport.py           # UK city transport (domestic flights + train estimates)
├── build_spreadsheet.py      # XLSX generation
├── config.py                 # Airport mappings, date ranges, constants
├── requirements.txt
├── data/
│   ├── imoova_deals.json     # Cached Imoova results
│   ├── flight_cache/         # Per-route cached API responses
│   └── api_log.json          # API call log
├── output/
│   └── holiday_options.xlsx  # Final output
└── docs/
    └── superpowers/specs/    # This file
```

### Dependencies

- `httpx` — HTTP client for API calls
- `playwright` — browser automation for Imoova scraping
- `openpyxl` — spreadsheet generation
- `python-dotenv` — .env file loading

## Component Details

### 1. scrape_imoova.py

**Input:** Imoova Europe deals page (`https://www.imoova.com/imoova-deals/europe`)

**Strategy:**
1. First inspect the page's network requests for an underlying JSON API (XHR/fetch calls returning deal data). If found, use `httpx` to hit that endpoint directly.
2. If no API found, use Playwright to render the page and extract deals from the DOM.

**Data extracted per deal:**
- Pickup city & country
- Dropoff city & country
- Pickup date (or earliest available date)
- Number of drive days
- Vehicle type
- Price
- Fuel/mileage allowances or conditions
- Booking link or deal reference

**Filtering:**
- Drive days between 5 and 10 (inclusive)
- Pickup date between 28 March and `(10 April - drive_days)` inclusive. For example, a 7-day drive must start by 3 April; a 5-day drive can start as late as 5 April.
- At least one city outside the UK
- If Imoova shows a date range for pickup, use the earliest date that falls within our window.

**Output:** `data/imoova_deals.json` — JSON object with two top-level keys: `raw` (all scraped deals) and `filtered` (deals passing the above criteria). Downstream modules consume `filtered` only.

### 2. search_flights.py

**API stack:**
- **Primary:** SerpAPI Google Flights (`engine=google_flights`)
- **Fallback:** Searchapi.io Google Flights (same engine, different provider)

Both return structured JSON with exact prices, airlines, flight numbers, departure/arrival times and airports.

**SerpAPI parameters:**
- `engine=google_flights`
- `type=2` (one-way)
- `departure_id` / `arrival_id` = IATA airport codes
- `outbound_date` = YYYY-MM-DD
- `currency=GBP`
- `hl=en`

Response contains `best_flights` and `other_flights` arrays. Each flight object includes airline, flight number, departure airport, arrival airport, departure time, arrival time, price, duration, number of stops.

**Search strategy per deal:**
- **Outbound:** London → Pickup City. Search day of pickup and (if pickup is after 28 March) the day before pickup. Never search before 28 March.
- **Return:** Dropoff City → London. Search last drive day and day after (if day after is on or before 10 April).
- For multi-airport cities, search all relevant airports and take the cheapest.
- Return top 3 cheapest flights per leg across all searched dates.

**Combining flights into trip options:** Each deal produces exactly 1 row in the spreadsheet, using the cheapest outbound flight and the cheapest return flight. The top 3 per leg are stored in the cache for reference (and could be shown in a detail view), but the spreadsheet row uses the single cheapest combination. If we wanted 9 combos per deal (3x3), the spreadsheet would balloon — one row per deal keeps it scannable.

**City → IATA mapping:**
- `config.py` holds a dictionary of known European city → IATA code(s).
- Multi-airport cities map to all codes (e.g. London → LHR/LGW/STN/LTN/SEN, Paris → CDG/ORY).
- SerpAPI also accepts city names directly, so unknown cities can be tried. If both the IATA lookup and city-name search return no results, log a warning and mark the deal as "airport not found" in the spreadsheet.

**Rate limiting & caching:**
- 1.5-second delay between API calls.
- Responses cached in `data/flight_cache/{IATA_from}_{IATA_to}_{date}.json` (always using IATA codes as keys, not city names).
- Cache TTL: 6 hours. If a cached file exists and is fresh, skip the API call.
- Every API call logged to `data/api_log.json` (endpoint, params, status code, result count, timestamp).

**Fallback logic:** If SerpAPI returns an error or empty results for a route, retry with Searchapi.io using equivalent parameters.

### 3. uk_transport.py

Handles cases where the Imoova pickup or dropoff is a UK city that isn't London.

**Two options checked:**
1. **Domestic flight** — searched via SerpAPI, same as international flights but UK routes (e.g. MAN→STN).
2. **Train estimate** — conservative hardcoded prices, flagged as "ESTIMATE" in output:
   - Manchester → London: £25
   - Birmingham → London: £15
   - Edinburgh → London: £40
   - Glasgow → London: £40
   - Bristol → London: £20
   - Leeds → London: £25
   - Liverpool → London: £25
   - Southampton → London: £15
   - Newcastle → London: £30

Returns whichever is cheaper. Train estimates clearly labelled so the user knows which prices are real and which are approximate.

**UK cities to handle:** Manchester, Birmingham, Edinburgh, Glasgow, Bristol, Leeds, Liverpool, Southampton, Newcastle.

### 4. build_spreadsheet.py

Creates `output/holiday_options.xlsx` with 4 sheets:

**Sheet 1: "All Options"** — sorted by total cost ascending.

Columns: Rank | Pickup City | Dropoff City | Pickup Date | Drive Days | Vehicle | Imoova £ | Outbound Flight | Outbound Date | Outbound Airline | Outbound Airports | Outbound £ | Return Flight | Return Date | Return Airline | Return Airports | Return £ | UK Transport £ | TOTAL £ | Imoova Link | Flight Search Link

Formatting:
- Top 10 rows highlighted green
- Conditional colouring on TOTAL: green < £80, yellow £80–150, red > £150
- Flight Search Link = Google Flights deeplink for verification/booking, constructed as: `https://www.google.com/travel/flights/search?tfs=...` using the standard Google Flights URL encoding for source, destination, and date. Alternatively, a simpler format: `https://www.google.com/travel/flights?q=Flights+from+{from_city}+to+{to_city}+on+{date}`

**Sheet 2: "Top 10 Cheapest"** — same columns, only the 10 best options.

**Sheet 3: "Flight Price Grid"** — two sub-tables:
- "London → City" — rows = European cities, columns = dates, cells = cheapest one-way price
- "City → London" — same structure, opposite direction

**Sheet 4: "Raw Data Log"** — every API call made: endpoint, parameters, response status, number of results, timestamp. Any errors or cities where flights couldn't be found.

### 5. Terminal Summary

After spreadsheet generation, print top 5 options to stdout with:
- Total cost
- Imoova deal details (route, days, dates, vehicle, price)
- Outbound flight (airline, flight number, date, airports, times, price)
- Return flight (same detail)
- UK transport if applicable

### config.py

Contains:
- `LONDON_AIRPORTS = ["LHR", "LGW", "STN", "LTN", "SEN"]`
- `CITY_AIRPORTS` dict mapping city names to IATA codes
- `UK_TRAIN_ESTIMATES` dict with conservative prices
- `UK_CITIES` set of UK city names
- Date range constants
- API endpoint URLs

### .env

```
SERPAPI_KEY=...
SEARCHAPI_KEY=...
```

## Error Handling

- If an API call fails for a city pair, log it and mark that option as "flight price unavailable" in the spreadsheet. Never substitute a guess.
- If Imoova page structure changes, fail loudly with a clear error message about what element wasn't found.
- If all flight APIs fail for a route, the option still appears in the spreadsheet but with blank flight columns and a note.

## Setup

1. `pip install -r requirements.txt`
2. `playwright install chromium`
3. Copy `.env.example` to `.env` and add API keys
4. `python main.py`

## Notes

- **Imoova currency:** If deals are listed in EUR, convert to GBP using a hardcoded rate (e.g. 0.86) in `config.py`. Flag converted prices with "(converted)" in the spreadsheet.
- **Expected API volume:** Roughly 20-40 deals × 2 legs × 2-3 dates × 1-3 airports = 100-300 SerpAPI calls. Well within typical free/starter tier limits.
- **Imoova scraping retries:** If the page fails to load, retry up to 3 times with 5-second waits before giving up.
- **Max total cost filter:** Options over £300 total are excluded from the spreadsheet to keep it focused. This threshold is configurable in `config.py`.

## What This Does NOT Do

- No train scraping (Trainline). Train prices are conservative estimates only.
- No account creation or booking — just finds and ranks options.
- No historical price tracking or fare prediction.
