from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import EventDB
from app.models import FunnelResponse, FunnelStage


def get_funnel(store_id: str, db: Session) -> FunnelResponse:

    # Stage 1 — unique visitors who entered (non-staff)
    # REENTRY events don't count as new visitors
    entry_visitors = db.query(func.distinct(EventDB.visitor_id))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "ENTRY",
            EventDB.is_staff   == False
        ).all()
    entry_ids = {row[0] for row in entry_visitors}
    entry_count = len(entry_ids)

    # Stage 2 — visitors who entered at least one named zone
    zone_visitors = db.query(func.distinct(EventDB.visitor_id))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "ZONE_ENTER",
            EventDB.is_staff   == False,
            EventDB.visitor_id.in_(entry_ids)
        ).all()
    zone_ids = {row[0] for row in zone_visitors}
    zone_count = len(zone_ids)

    # Stage 3 — visitors who joined the billing queue
    billing_visitors = db.query(func.distinct(EventDB.visitor_id))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "BILLING_QUEUE_JOIN",
            EventDB.is_staff   == False,
            EventDB.visitor_id.in_(entry_ids)
        ).all()
    billing_ids = {row[0] for row in billing_visitors}
    billing_count = len(billing_ids)

    # Stage 4 — visitors who purchased
    # = billing visitors who did NOT abandon
    abandoned_visitors = db.query(func.distinct(EventDB.visitor_id))\
        .filter(
            EventDB.store_id   == store_id,
            EventDB.event_type == "BILLING_QUEUE_ABANDON",
            EventDB.is_staff   == False
        ).all()
    abandoned_ids = {row[0] for row in abandoned_visitors}
    purchased_ids = billing_ids - abandoned_ids
    purchase_count = len(purchased_ids)

    # Calculate drop-off percentages
    def drop_off(current, previous):
        if previous == 0:
            return 0.0
        return round((1 - current / previous) * 100, 1)

    stages = [
        FunnelStage(
            stage        = "Entry",
            count        = entry_count,
            drop_off_pct = 0.0
        ),
        FunnelStage(
            stage        = "Zone Visit",
            count        = zone_count,
            drop_off_pct = drop_off(zone_count, entry_count)
        ),
        FunnelStage(
            stage        = "Billing Queue",
            count        = billing_count,
            drop_off_pct = drop_off(billing_count, zone_count)
        ),
        FunnelStage(
            stage        = "Purchase",
            count        = purchase_count,
            drop_off_pct = drop_off(purchase_count, billing_count)
        ),
    ]

    return FunnelResponse(store_id=store_id, stages=stages)