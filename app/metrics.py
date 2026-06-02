from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import EventDB
from app.models import MetricsResponse, ZoneDwell
from datetime import datetime, timedelta


def get_metrics(store_id: str, db: Session) -> MetricsResponse:

    # --- Unique visitors (non-staff ENTRY events) ---
    unique_visitors = db.query(func.count(func.distinct(EventDB.visitor_id)))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "ENTRY",
            EventDB.is_staff   == False
        ).scalar() or 0

    # --- Converted visitors ---
    # A visitor is converted if they have a BILLING_QUEUE_JOIN event
    # and no BILLING_QUEUE_ABANDON event (i.e. they stayed and bought)
    abandoned_visitors = db.query(func.distinct(EventDB.visitor_id))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "BILLING_QUEUE_ABANDON",
            EventDB.is_staff   == False
        ).all()
    abandoned_ids = {row[0] for row in abandoned_visitors}

    billing_visitors = db.query(func.distinct(EventDB.visitor_id))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "BILLING_QUEUE_JOIN",
            EventDB.is_staff   == False
        ).all()
    billing_ids = {row[0] for row in billing_visitors}

    converted = len(billing_ids - abandoned_ids)

    conversion_rate = round(converted / unique_visitors, 4) if unique_visitors > 0 else 0.0

    # --- Avg dwell per zone ---
    dwell_rows = db.query(EventDB.zone_id, func.avg(EventDB.dwell_ms))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "ZONE_DWELL",
            EventDB.is_staff   == False,
            EventDB.zone_id    != None
        )\
        .group_by(EventDB.zone_id)\
        .all()

    avg_dwell_per_zone = [
        ZoneDwell(zone_id=row[0], avg_dwell_ms=round(row[1], 2))
        for row in dwell_rows
    ]

    # --- Current queue depth ---
    latest_queue = db.query(EventDB.queue_depth)\
        .filter(
            EventDB.store_id    == store_id,
            EventDB.event_type  == "BILLING_QUEUE_JOIN",
            EventDB.queue_depth != None
        )\
        .order_by(EventDB.timestamp.desc())\
        .first()

    queue_depth = latest_queue[0] if latest_queue else 0

    # --- Abandonment rate ---
    total_billing = len(billing_ids)
    abandonment_rate = round(len(abandoned_ids) / total_billing, 4) if total_billing > 0 else 0.0

    return MetricsResponse(
        store_id          = store_id,
        unique_visitors   = unique_visitors,
        conversion_rate   = conversion_rate,
        avg_dwell_per_zone= avg_dwell_per_zone,
        queue_depth       = queue_depth,
        abandonment_rate  = abandonment_rate,
    )