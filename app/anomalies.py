from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import EventDB
from app.models import AnomalyResponse, Anomaly
from datetime import datetime, timedelta


def get_anomalies(store_id: str, db: Session) -> AnomalyResponse:
    anomalies = []
    now = datetime.utcnow()

    # --- Anomaly 1: Billing queue spike ---
    latest_queue = db.query(EventDB.queue_depth)\
        .filter(
            EventDB.store_id    == store_id,
            EventDB.event_type  == "BILLING_QUEUE_JOIN",
            EventDB.queue_depth != None
        )\
        .order_by(EventDB.timestamp.desc())\
        .first()

    if latest_queue:
        depth = latest_queue[0]
        if depth >= 10:
            anomalies.append(Anomaly(
                anomaly_type     = "BILLING_QUEUE_SPIKE",
                severity         = "CRITICAL",
                description      = f"Queue depth is {depth} — severely backed up.",
                suggested_action = "Open additional billing counter immediately."
            ))
        elif depth >= 5:
            anomalies.append(Anomaly(
                anomaly_type     = "BILLING_QUEUE_SPIKE",
                severity         = "WARN",
                description      = f"Queue depth is {depth} — building up.",
                suggested_action = "Call another staff member to billing counter."
            ))

    # --- Anomaly 2: Conversion drop ---
    total_entries = db.query(func.count(func.distinct(EventDB.visitor_id)))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "ENTRY",
            EventDB.is_staff   == False
        ).scalar() or 0

    total_purchases = db.query(func.count(func.distinct(EventDB.visitor_id)))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "BILLING_QUEUE_JOIN",
            EventDB.is_staff   == False
        ).scalar() or 0

    abandoned = db.query(func.count(func.distinct(EventDB.visitor_id)))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "BILLING_QUEUE_ABANDON",
            EventDB.is_staff   == False
        ).scalar() or 0

    converted = total_purchases - abandoned
    current_rate = converted / total_entries if total_entries > 0 else 0

    if total_entries >= 5 and current_rate < 0.20:
        anomalies.append(Anomaly(
            anomaly_type     = "CONVERSION_DROP",
            severity         = "WARN",
            description      = f"Conversion rate is {round(current_rate * 100, 1)}% — below 20% threshold.",
            suggested_action = "Check promotions, staffing, or billing wait times."
        ))

    # --- Anomaly 3: Dead zone (no visits in last 30 minutes) ---
    cutoff = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    active_zones = db.query(func.distinct(EventDB.zone_id))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "ZONE_ENTER",
            EventDB.timestamp  >= cutoff,
            EventDB.zone_id    != None
        ).all()
    active_zone_ids = {row[0] for row in active_zones}

    all_zones = db.query(func.distinct(EventDB.zone_id))\
        .filter(
            EventDB.store_id == store_id,
            EventDB.zone_id  != None
        ).all()
    all_zone_ids = {row[0] for row in all_zones}

    dead_zones = all_zone_ids - active_zone_ids
    for zone in dead_zones:
        anomalies.append(Anomaly(
            anomaly_type     = "DEAD_ZONE",
            severity         = "INFO",
            description      = f"Zone {zone} has had no visits in the last 30 minutes.",
            suggested_action = f"Consider moving promotional display to {zone}."
        ))

    return AnomalyResponse(store_id=store_id, anomalies=anomalies)