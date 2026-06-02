from sqlalchemy.orm import Session
from app.database import EventDB
from app.models import HealthResponse
from datetime import datetime, timedelta


def get_health(db: Session) -> HealthResponse:

    # Get the most recent event timestamp across all stores
    latest = db.query(EventDB.timestamp)\
        .order_by(EventDB.timestamp.desc())\
        .first()

    last_event_timestamp = latest[0] if latest else None

    # Check if feed is stale — no events in last 10 minutes
    stale_feed = True
    if last_event_timestamp:
        try:
            last_time = datetime.fromisoformat(
                last_event_timestamp.replace("Z", "+00:00")
            )
            cutoff = datetime.now(last_time.tzinfo) - timedelta(minutes=10)
            stale_feed = last_time < cutoff
        except Exception:
            stale_feed = True

    return HealthResponse(
        status               = "ok",
        last_event_timestamp = last_event_timestamp,
        stale_feed           = stale_feed,
    )