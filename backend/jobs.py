"""
Job manager for the Imoova Holiday Optimiser backend.
Manages search jobs in-memory with WebSocket notification support.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set

import httpx

from fastapi import WebSocket

import config
from models import SearchRequest
from scraper import scrape_all_deals, filter_deals, ScrapingError
from flights import (
    search_flights_for_deal,
    presearch_unique_routes,
    close_browser,
)

logger = logging.getLogger(__name__)

# ── In-memory job store ───────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}
_job_websockets: Dict[str, Set[WebSocket]] = {}
JOB_EXPIRY_SECONDS = 3600  # 1 hour


def create_job(request: SearchRequest) -> str:
    """Create a new job and return its ID."""
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "id": job_id,
        "request": request,
        "status": "queued",
        "message": "Queued",
        "total_deals": 0,
        "searched_deals": 0,
        "total_routes": 0,
        "searched_routes": 0,
        "results": [],
        "complete_results": 0,
        "created_at": time.time(),
        "error": None,
    }
    _job_websockets[job_id] = set()
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a job by ID, or None if not found / expired."""
    job = _jobs.get(job_id)
    if job is None:
        return None
    if time.time() - job["created_at"] > JOB_EXPIRY_SECONDS:
        _cleanup_job(job_id)
        return None
    return job


def get_job_results(job_id: str) -> Optional[List[Dict[str, Any]]]:
    """Get results for a job."""
    job = get_job(job_id)
    if job is None:
        return None
    return job["results"]


def register_websocket(job_id: str, ws: WebSocket) -> None:
    """Register a WebSocket connection for a job."""
    if job_id not in _job_websockets:
        _job_websockets[job_id] = set()
    _job_websockets[job_id].add(ws)


def unregister_websocket(job_id: str, ws: WebSocket) -> None:
    """Remove a WebSocket connection for a job."""
    if job_id in _job_websockets:
        _job_websockets[job_id].discard(ws)


async def _notify(job_id: str, message: Dict[str, Any]) -> None:
    """Send a JSON message to all connected WebSockets for a job."""
    if job_id not in _job_websockets:
        return

    dead: List[WebSocket] = []
    for ws in _job_websockets[job_id]:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)

    for ws in dead:
        _job_websockets[job_id].discard(ws)


def _cleanup_job(job_id: str) -> None:
    """Remove an expired job."""
    _jobs.pop(job_id, None)
    _job_websockets.pop(job_id, None)


def cleanup_expired_jobs() -> int:
    """Remove all expired jobs. Returns count of removed jobs."""
    now = time.time()
    expired = [
        jid
        for jid, job in _jobs.items()
        if now - job["created_at"] > JOB_EXPIRY_SECONDS
    ]
    for jid in expired:
        _cleanup_job(jid)
    return len(expired)


async def _keep_alive(job_id: str) -> None:
    """Self-ping to keep Render free tier awake during long jobs."""
    port = int(os.environ.get("PORT", "10000"))
    url = f"http://localhost:{port}/health"
    try:
        async with httpx.AsyncClient() as client:
            while job_id in _jobs and _jobs[job_id]["status"] not in ("complete", "error"):
                await asyncio.sleep(20)
                try:
                    await client.get(url, timeout=5)
                except Exception:
                    pass
    except asyncio.CancelledError:
        pass


async def run_job(job_id: str) -> None:
    """
    Main job pipeline:
    1. Scrape Imoova deals
    2. Filter by user params
    3. Pre-search unique flight routes
    4. Enrich each deal with flight data
    5. Push results via WebSocket as they come in
    """
    job = _jobs.get(job_id)
    if job is None:
        return

    request: SearchRequest = job["request"]

    # Keep-alive: ping ourselves every 20s to prevent Render free tier spin-down
    keep_alive_task = asyncio.create_task(_keep_alive(job_id))

    try:
        # ── Step 1: Scrape Imoova ─────────────────────────────
        job["status"] = "scraping"
        job["message"] = "Scraping Imoova deals..."
        await _notify(job_id, {
            "type": "status",
            "step": "scraping",
            "message": "Scraping Imoova deals...",
        })

        raw_deals = await scrape_all_deals()
        logger.info("Scraped %d raw deals", len(raw_deals))

        # ── Step 2: Filter deals ──────────────────────────────
        job["status"] = "filtering"
        earliest_str = request.earliest_departure or (date.today() + timedelta(days=3)).isoformat()
        latest_str = request.latest_return or (date.today() + timedelta(days=28)).isoformat()
        earliest = date.fromisoformat(earliest_str)
        latest = date.fromisoformat(latest_str)

        filtered = filter_deals(
            raw_deals,
            earliest_departure=earliest,
            latest_return=latest,
            min_days=request.min_days,
            max_days=request.max_days,
            min_seats=request.min_seats,
        )

        job["total_deals"] = len(filtered)
        filter_msg = f"Found {len(raw_deals)} deals, {len(filtered)} match your dates"
        job["message"] = filter_msg
        await _notify(job_id, {
            "type": "status",
            "step": "filtering",
            "message": filter_msg,
        })

        if not filtered:
            job["status"] = "complete"
            job["message"] = "No deals match your search criteria"
            await _notify(job_id, {
                "type": "complete",
                "total_results": 0,
                "complete_results": 0,
            })
            return

        # ── Step 3: Resolve home airports ─────────────────────
        home_airports = config.get_airports_for_city(request.home_city)
        if not home_airports:
            job["status"] = "error"
            job["error"] = f"No airports found for city '{request.home_city}'"
            job["message"] = job["error"]
            await _notify(job_id, {
                "type": "status",
                "step": "error",
                "message": job["error"],
            })
            return

        # ── Step 4: Pre-search unique flight routes ───────────
        job["status"] = "searching"
        job["message"] = "Searching flights..."
        await _notify(job_id, {
            "type": "status",
            "step": "flights",
            "message": "Searching flights...",
        })

        search_start = time.time()

        async def on_route_progress(searched: int, total: int) -> None:
            elapsed = time.time() - search_start
            if searched > 0:
                per_route = elapsed / searched
                remaining = (total - searched) * per_route
            else:
                remaining = 0

            job["searched_routes"] = searched
            job["total_routes"] = total
            await _notify(job_id, {
                "type": "progress",
                "step": "flights",
                "searched": searched,
                "total": total,
                "eta_seconds": round(remaining, 1),
            })

        await presearch_unique_routes(
            filtered, home_airports, earliest, latest, on_route_progress
        )

        # ── Step 5: Enrich each deal ──────────────────────────
        total = len(filtered)
        for i, deal in enumerate(filtered, 1):
            try:
                enriched = await search_flights_for_deal(
                    deal, request.home_city, home_airports,
                    earliest, latest,
                )
                job["results"].append(enriched)
                if enriched.get("is_complete"):
                    job["complete_results"] += 1

                job["searched_deals"] = i

                await _notify(job_id, {
                    "type": "result",
                    "deal": enriched,
                })

            except Exception as e:
                logger.warning("Error enriching deal %s: %s", deal.get("ref", "?"), e)
                error_deal = {
                    "deal": {
                        "pickup_city": deal.get("pickup_city", ""),
                        "pickup_country": config.CITY_COUNTRIES.get(deal.get("pickup_city", ""), ""),
                        "dropoff_city": deal.get("dropoff_city", ""),
                        "dropoff_country": config.CITY_COUNTRIES.get(deal.get("dropoff_city", ""), ""),
                        "pickup_date": deal.get("depart_date", ""),
                        "dropoff_date": deal.get("deliver_date", ""),
                        "drive_days": deal.get("drive_days", 0),
                        "vehicle_type": deal.get("vehicle", ""),
                        "seats": deal.get("seats", 0),
                        "imoova_price_gbp": deal.get("rate_gbp", 0),
                        "imoova_url": deal.get("deal_url", ""),
                    },
                    "drive_hours": None,
                    "outbound_flight": None,
                    "return_flight": None,
                    "outbound_is_home": False,
                    "return_is_home": False,
                    "total_price_gbp": None,
                    "google_flights_outbound_url": None,
                    "google_flights_return_url": None,
                    "is_complete": False,
                    "warnings": [f"Search failed: {e}"],
                }
                job["results"].append(error_deal)
                job["searched_deals"] = i

        # ── Step 6: Sort and complete ─────────────────────────
        job["results"].sort(key=lambda x: x.get("total_price_gbp") or 9999)
        job["status"] = "complete"
        job["message"] = "Search complete"
        await _notify(job_id, {
            "type": "complete",
            "total_results": len(job["results"]),
            "complete_results": job["complete_results"],
        })

    except ScrapingError as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["message"] = f"Scraping failed: {e}"
        await _notify(job_id, {
            "type": "status",
            "step": "error",
            "message": job["message"],
        })
        logger.error("Scraping error for job %s: %s", job_id, e)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("Unexpected error for job %s:\n%s", job_id, tb)
        job["status"] = "error"
        job["error"] = str(e)
        job["message"] = f"Unexpected error: {e}\n{tb[-500:]}"
        await _notify(job_id, {
            "type": "status",
            "step": "error",
            "message": job["message"],
        })
        logger.error("Unexpected error for job %s: %s", job_id, e, exc_info=True)

    finally:
        keep_alive_task.cancel()
