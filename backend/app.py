"""
FastAPI application for the Imoova Holiday Optimiser backend.
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
    title="Imoova Holiday Optimiser",
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
    return {"status": "ok", "version": "8"}


@app.get("/api/debug/jobs")
async def debug_jobs() -> dict:
    """Debug endpoint: list active jobs."""
    import time as _time
    from jobs import _jobs
    summary = {}
    for jid, job in _jobs.items():
        summary[jid] = {
            "status": job["status"],
            "message": job.get("message", ""),
            "total_deals": job.get("total_deals", 0),
            "searched_deals": job.get("searched_deals", 0),
            "results_count": len(job.get("results", [])),
            "age_seconds": round(_time.time() - job["created_at"], 1),
        }
    return {"active_jobs": len(summary), "jobs": summary}


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

    async def _run_with_logging(jid: str) -> None:
        try:
            logger.info("Starting job %s", jid)
            await run_job(jid)
            logger.info("Job %s completed", jid)
        except Exception:
            logger.exception("Job %s crashed", jid)

    asyncio.create_task(_run_with_logging(job_id))
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
    """
    Poll-based WebSocket handler. Instead of relying on push notifications
    from run_job (which causes concurrent read/write issues on the same
    WebSocket), this handler polls the job state every 2 seconds and sends
    any new updates to the client.
    """
    await ws.accept()

    job = get_job(job_id)
    if job is None:
        await ws.send_json({"type": "error", "message": "Job not found or expired"})
        await ws.close()
        return

    last_status = ""
    last_message = ""
    last_searched_routes = 0
    last_results_sent = 0
    ping_counter = 0

    try:
        while True:
            job = get_job(job_id)
            if job is None:
                await ws.send_json({"type": "error", "message": "Job expired"})
                break

            status = job["status"]
            message = job.get("message", "")
            sent_something = False

            # Send status updates when they change
            if status != last_status or message != last_message:
                if status == "error":
                    await ws.send_json({
                        "type": "error",
                        "message": message,
                    })
                    break
                elif status in ("scraping", "filtering", "searching"):
                    step = "flights" if status == "searching" else status
                    await ws.send_json({
                        "type": "status",
                        "step": step,
                        "message": message,
                    })
                    sent_something = True
                last_status = status
                last_message = message

            # Send flight search progress
            if status == "searching":
                searched_routes = job.get("searched_routes", 0)
                total_routes = job.get("total_routes", 0)
                if searched_routes != last_searched_routes and total_routes > 0:
                    await ws.send_json({
                        "type": "progress",
                        "step": "flights",
                        "searched": searched_routes,
                        "total": total_routes,
                        "eta_seconds": 0,
                    })
                    last_searched_routes = searched_routes
                    sent_something = True

            # Send new results as they arrive
            all_results = job.get("results", [])
            if len(all_results) > last_results_sent:
                for enriched in all_results[last_results_sent:]:
                    await ws.send_json({"type": "result", "deal": enriched})
                last_results_sent = len(all_results)
                sent_something = True

            # Send completion
            if status == "complete":
                await ws.send_json({
                    "type": "complete",
                    "total_results": len(all_results),
                    "complete_results": job.get("complete_results", 0),
                })
                break

            # Send keepalive ping every ~10s to prevent Render proxy from
            # dropping the connection during long-running phases like scraping
            ping_counter += 1
            if not sent_something and ping_counter % 2 == 0:
                await ws.send_json({"type": "ping"})

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error for job %s: %s", job_id, e)
