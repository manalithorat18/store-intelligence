import time
import uuid
import structlog
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, create_tables
from app.models import (
    IngestRequest, IngestResponse,
    MetricsResponse, FunnelResponse,
    HeatmapResponse, HeatmapZone,
    AnomalyResponse, HealthResponse
)
from app.ingestion import ingest_events
from app.metrics import get_metrics
from app.funnel import get_funnel
from app.anomalies import get_anomalies
from app.health import get_health
from app.database import EventDB
from sqlalchemy import func

log = structlog.get_logger()

app = FastAPI(title="Store Intelligence API", version="1.0.0")


@app.on_event("startup")
def startup():
    create_tables()
    log.info("startup", message="Database tables created")


# ── Ingest ────────────────────────────────────────────────────────────────────

@app.post("/events/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest, db: Session = Depends(get_db)):
    trace_id = str(uuid.uuid4())[:8]
    start    = time.time()

    result = ingest_events(request, db)

    log.info("ingest",
        trace_id    = trace_id,
        endpoint    = "/events/ingest",
        event_count = len(request.events),
        accepted    = result.accepted,
        rejected    = result.rejected,
        latency_ms  = round((time.time() - start) * 1000, 2),
        status_code = 200
    )
    return result


# ── Metrics ───────────────────────────────────────────────────────────────────

@app.get("/stores/{store_id}/metrics", response_model=MetricsResponse)
def metrics(store_id: str, db: Session = Depends(get_db)):
    trace_id = str(uuid.uuid4())[:8]
    start    = time.time()

    result = get_metrics(store_id, db)

    log.info("metrics",
        trace_id   = trace_id,
        store_id   = store_id,
        endpoint   = f"/stores/{store_id}/metrics",
        latency_ms = round((time.time() - start) * 1000, 2),
        status_code= 200
    )
    return result


# ── Funnel ────────────────────────────────────────────────────────────────────

@app.get("/stores/{store_id}/funnel", response_model=FunnelResponse)
def funnel(store_id: str, db: Session = Depends(get_db)):
    trace_id = str(uuid.uuid4())[:8]
    start    = time.time()

    result = get_funnel(store_id, db)

    log.info("funnel",
        trace_id   = trace_id,
        store_id   = store_id,
        endpoint   = f"/stores/{store_id}/funnel",
        latency_ms = round((time.time() - start) * 1000, 2),
        status_code= 200
    )
    return result


# ── Heatmap ───────────────────────────────────────────────────────────────────

@app.get("/stores/{store_id}/heatmap", response_model=HeatmapResponse)
def heatmap(store_id: str, db: Session = Depends(get_db)):
    trace_id = str(uuid.uuid4())[:8]
    start    = time.time()

    db_rows = db.query(
        EventDB.zone_id,
        func.count(EventDB.event_id).label("visit_count"),
        func.avg(EventDB.dwell_ms).label("avg_dwell")
    ).filter(
        EventDB.store_id   == store_id,
        EventDB.event_type == "ZONE_ENTER",
        EventDB.is_staff   == False,
        EventDB.zone_id    != None
    ).group_by(EventDB.zone_id).all()

    zones = []
    if db_rows:
        max_count = max(row.visit_count for row in db_rows) or 1
        for row in db_rows:
            normalised = round((row.visit_count / max_count) * 100, 1)
            confidence = "low" if row.visit_count < 20 else "ok"
            zones.append(HeatmapZone(
                zone_id          = row.zone_id,
                visit_frequency  = row.visit_count,
                avg_dwell_ms     = round(row.avg_dwell or 0, 2),
                normalised_score = normalised,
                data_confidence  = confidence
            ))

    log.info("heatmap",
        trace_id   = trace_id,
        store_id   = store_id,
        endpoint   = f"/stores/{store_id}/heatmap",
        latency_ms = round((time.time() - start) * 1000, 2),
        status_code= 200
    )
    return HeatmapResponse(store_id=store_id, zones=zones)


# ── Anomalies ─────────────────────────────────────────────────────────────────

@app.get("/stores/{store_id}/anomalies", response_model=AnomalyResponse)
def anomalies(store_id: str, db: Session = Depends(get_db)):
    trace_id = str(uuid.uuid4())[:8]
    start    = time.time()

    result = get_anomalies(store_id, db)

    log.info("anomalies",
        trace_id   = trace_id,
        store_id   = store_id,
        endpoint   = f"/stores/{store_id}/anomalies",
        latency_ms = round((time.time() - start) * 1000, 2),
        status_code= 200
    )
    return result


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    return get_health(db)