"""
FastAPI application for the Imoova Holiday Optimizer backend.
REST endpoints for job management + WebSocket for live progress.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from models import SearchRequest, JobStatus
from jobs import (
    create_job,
    get_job,
    get_job_results,
    register_websocket,
    unregister_websocket,
    run_job,
    cleanup_expired_jobs,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────

app = FastAPI(
    title="Imoova Holiday Optimizer",
    version="1.0.0",
    description="Find cheap campervan relocation holidays with flight prices.",
)

# CORS
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:3000")
cors_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Background cleanup task ───────────────────────────────────

@app.on_event("startup")
async def startup_cleanup_loop() -> None:
    """Periodically clean up expired jobs."""

    async def _loop() -> None:
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            removed = cleanup_expired_jobs()
            if removed:
                logger.info("Cleaned up %d expired jobs", removed)

    asyncio.create_task(_loop())


# ── Health check ──────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "4"}


@app.get("/api/debug/scrape")
async def debug_scrape() -> dict:
    """Debug endpoint: scrape Imoova and return raw results."""
    from scraper import scrape_all_deals
    try:
        deals = await scrape_all_deals()
        sample = deals[:3] if deals else []
        bad = [d for d in deals if not d.get("depart_date") or not d.get("deliver_date")]
        return {
            "total_raw": len(deals),
            "bad_dates": len(bad),
            "bad_samples": bad[:5],
            "sample_deals": sample,
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


# ── City list for autocomplete ────────────────────────────────

@app.get("/api/cities")
async def cities() -> List[dict]:
    return config.get_city_list()


# ── Create search job ────────────────────────────────────────

@app.post("/api/search")
async def search(request: SearchRequest) -> dict:
    # Validate home city has airports
    airports = config.get_airports_for_city(request.home_city)
    if not airports:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown city: '{request.home_city}'"},
        )

    job_id = create_job(request)
    # Use asyncio.create_task so run_job stays on the event loop
    # (BackgroundTasks runs in a threadpool which breaks async WebSocket notifications)
    asyncio.create_task(run_job(job_id))
    return {"job_id": job_id}


# ── Get results (for page refresh / reconnect) ───────────────

@app.get("/api/results/{job_id}")
async def results(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Job not found or expired"},
        )

    job_results = get_job_results(job_id) or []
    return {
        "job_id": job_id,
        "status": job["status"],
        "message": job.get("message", ""),
        "total_deals": job.get("total_deals", 0),
        "searched_deals": job.get("searched_deals", 0),
        "results": job_results,
        "complete_results": job.get("complete_results", 0),
    }


# ── WebSocket for live progress ──────────────────────────────

@app.websocket("/ws/job/{job_id}")
async def websocket_job(ws: WebSocket, job_id: str) -> None:
    await ws.accept()

    job = get_job(job_id)
    if job is None:
        await ws.send_json({"type": "error", "message": "Job not found or expired"})
        await ws.close()
        return

    register_websocket(job_id, ws)

    # If the job already has results, send them all immediately (reconnect case)
    existing_results = job.get("results", [])
    if existing_results:
        for enriched in existing_results:
            try:
                await ws.send_json({"type": "result", "deal": enriched})
            except Exception:
                unregister_websocket(job_id, ws)
                return

    # If already complete, send completion message
    if job["status"] == "complete":
        try:
            await ws.send_json({
                "type": "complete",
                "total_results": len(existing_results),
                "complete_results": job.get("complete_results", 0),
            })
        except Exception:
            pass
        unregister_websocket(job_id, ws)
        return

    if job["status"] == "error":
        try:
            await ws.send_json({
                "type": "status",
                "step": "error",
                "message": job.get("message", "Unknown error"),
            })
        except Exception:
            pass
        unregister_websocket(job_id, ws)
        return

    # Keep connection alive with heartbeat pings while job runs
    try:
        while True:
            # Wait for a message (client might send pongs or close)
            # Use a timeout to send periodic pings
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=10.0)
            except asyncio.TimeoutError:
                # Send a heartbeat ping
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    break

            # Check if job is done
            current_job = get_job(job_id)
            if current_job is None or current_job["status"] in ("complete", "error"):
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        unregister_websocket(job_id, ws)
