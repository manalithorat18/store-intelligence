from sqlalchemy.orm import Session
from app.database import EventDB
from app.models import Event, IngestRequest, IngestResponse


def ingest_events(request: IngestRequest, db: Session) -> IngestResponse:
    accepted = 0
    rejected = 0
    errors = []

    for event in request.events:
        try:
            # Check if event_id already exists (idempotency)
            existing = db.query(EventDB).filter(
                EventDB.event_id == event.event_id
            ).first()

            if existing:
                # Already ingested — skip silently (idempotent)
                accepted += 1
                continue

            db_event = EventDB(
                event_id    = event.event_id,
                store_id    = event.store_id,
                camera_id   = event.camera_id,
                visitor_id  = event.visitor_id,
                event_type  = event.event_type.value,
                timestamp   = event.timestamp,
                zone_id     = event.zone_id,
                dwell_ms    = event.dwell_ms,
                is_staff    = event.is_staff,
                confidence  = event.confidence,
                queue_depth = event.metadata.queue_depth,
                sku_zone    = event.metadata.sku_zone,
                session_seq = event.metadata.session_seq,
            )
            db.add(db_event)
            db.commit()
            accepted += 1

        except Exception as e:
            rejected += 1
            errors.append(f"event_id={event.event_id}: {str(e)}")
            db.rollback()

    return IngestResponse(accepted=accepted, rejected=rejected, errors=errors)