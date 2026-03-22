# Imoova Holiday Optimizer — Web App Design

## Overview

Turn the existing Python CLI tool into a public-facing website. Users enter their home city and travel dates, wait while the backend scrapes Imoova deals and searches flights in real-time, then browse ranked results with filters.

## Architecture

**Frontend:** Next.js 15 (App Router) + Tailwind v4 on Vercel free tier
**Backend:** FastAPI + Playwright on Render free tier (Docker)
**Communication:** REST for job creation, WebSocket for live progress

```
[Vercel - Next.js Frontend]
    |
    | POST /api/search (create job)
    | WS /ws/job/{id} (live progress)
    | GET /api/results/{id} (full results)
    |
[Render - FastAPI Backend]
    |
    | Playwright browser (persistent, reused)
    |--- Scrapes Imoova deals
    |--- Searches Google Flights via fast-flights
    |--- Returns results via WebSocket as found
```

## Search Page (only required field: home city)

**Required:**
- Home city — autocomplete input, searches our airport database (~200 European cities)

**Optional (collapsed under "More options", sensible defaults):**
- Trip duration — range slider, default 5–10 days
- Min seats — dropdown, default "Any"
- Earliest departure — date picker, default "today + 3 days"
- Latest return — date picker, default "4 weeks from today"

One big "Find Holidays" button. That's it.

## Loading / Progress Screen

After submit, same page transitions to a progress view:
- Animated progress bar with step labels
- Steps: "Scraping Imoova deals..." → "Found X deals matching your dates" → "Searching flights... (14/87)" → "Almost done..."
- Estimated time remaining (based on routes left × ~3s each)
- Results cards start appearing below the progress bar as each deal gets priced
- User can scroll through partial results while search continues

## Results Page

**Each result card shows:**
- Total price (big, prominent)
- Route: Pickup City → Dropoff City with country flags
- Dates: pickup date, drive days, return date
- Vehicle type + seats
- Outbound flight: airline, route, time, price (or "Drive from home — £0" if home city = pickup city)
- Return flight: same detail (or "Drive home — £0" if home city = dropoff city)
- Imoova price
- "Book on Imoova" button (links to deal URL)
- "Check flights" button (Google Flights deeplink)

**Filters (top bar / sidebar):**
- Sort: price (default) / departure date / trip duration
- Country filter: toggle chips for each country in results
- City filter: deselect specific pickup/dropoff cities
- Max total price slider
- Hide incomplete results toggle (deals where flights couldn't be found)

**Edge cases:**
- User lives in a pickup city → outbound flight = £0, show "Drive from home"
- User lives in a dropoff city → return flight = £0, show "Drive home"
- No flights found for a leg → card shows "Flight price unavailable", greyed out, filtered out by default

## Backend API

### POST /api/search
```json
Request:
{
  "home_city": "Berlin",
  "min_days": 5,
  "max_days": 10,
  "min_seats": null,
  "earliest_departure": "2026-03-28",
  "latest_return": "2026-04-10"
}

Response:
{ "job_id": "abc123" }
```

### WS /ws/job/{job_id}
Server sends JSON messages:
```json
{"type": "status", "step": "scraping", "message": "Scraping Imoova deals..."}
{"type": "status", "step": "filtering", "message": "Found 125 deals, 87 match your dates"}
{"type": "progress", "step": "flights", "searched": 14, "total": 87, "eta_seconds": 220}
{"type": "result", "deal": { ... full enriched deal object ... }}
{"type": "complete", "total_results": 72, "complete_results": 65}
```

### GET /api/results/{job_id}
Returns full results array (for page refresh / sharing).

### GET /api/cities
Returns autocomplete list: `[{"name": "Berlin", "country": "Germany", "airports": ["BER"]}]`

## Backend Job Pipeline

1. Receive search params
2. Scrape Imoova (fresh, ~30-60s) — stream "scraping" status
3. Filter deals by user's date range, min days, max days, seats
4. Identify unique flight routes (home_city airports ↔ pickup/dropoff airports)
5. Search flights one by one via persistent Playwright browser — stream each result as found
6. For deals where home_city = pickup or dropoff city, skip that flight leg (£0)
7. Assemble final ranked results
8. Store results in memory (keyed by job_id, expire after 1 hour)

## Home City = Pickup/Dropoff Handling

When the user's home city matches a deal's pickup or dropoff city:
- **Home = pickup city:** No outbound flight needed. Total = Imoova price + return flight only.
- **Home = dropoff city:** No return flight needed. Total = Imoova price + outbound flight only.
- **Home = both:** Total = Imoova price only. (Rare but possible for round-trip deals.)
- Match by checking if the user's airports overlap with the deal city's airports (handles "Berlin" matching "Berlin Brandenburg" etc.)

## Project Structure

```
imoova-optimizer/
├── backend/                    # FastAPI Python backend
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py                  # FastAPI app, routes, WebSocket
│   ├── jobs.py                 # Job manager (in-memory store, async workers)
│   ├── scraper.py              # Imoova scraper (adapted from scrape_imoova.py)
│   ├── flights.py              # Flight search (adapted from search_flights.py)
│   ├── config.py               # Airport DB, constants
│   └── models.py               # Pydantic models for API
├── frontend/                   # Next.js frontend
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx            # Search + results (single page app)
│   │   └── globals.css
│   ├── components/
│   │   ├── SearchForm.tsx
│   │   ├── ProgressView.tsx
│   │   ├── ResultsList.tsx
│   │   ├── ResultCard.tsx
│   │   ├── Filters.tsx
│   │   └── CityAutocomplete.tsx
│   └── lib/
│       ├── api.ts              # API client
│       ├── types.ts            # TypeScript types
│       └── useSearch.ts        # Custom hook: manages job lifecycle
├── scrape_imoova.py            # Original CLI scripts (kept for reference)
├── search_flights.py
├── config.py
├── build_spreadsheet.py
├── main.py
└── output/
```

## Render Deployment

- Docker container with Python 3.11 + Playwright Chromium
- `render.yaml` for infrastructure-as-code
- Keep-alive ping every 10 min to avoid cold starts on free tier
- Single worker process (concurrent searches queue up)

## V2 Considerations (not built now)

- Domestic travel options when pickup city is near home
- User accounts + saved searches
- Price alerts / email notifications
- Multi-city trip chaining (Berlin → Lyon → Barcelona)
- Mobile app
