# System Design

## Architecture Overview

┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CCTV Clips     │────▶│  Detection Layer │────▶│  Event Stream   │
│  (5 cameras)    │     │  YOLOv8n +       │     │  data/events    │
│                 │     │  ByteTrack       │     │  .jsonl         │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
│
▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Live Metrics   │◀────│  Intelligence    │◀────│  POST /events   │
│  /metrics       │     │  API (FastAPI)   │     │  /ingest        │
│  /funnel        │     │  SQLite          │     │                 │
│  /anomalies     │     │                 │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘

## Component Responsibilities

### pipeline/detect.py
- Loads YOLOv8n model (pretrained on COCO, class 0 = person)
- Runs ByteTrack multi-object tracking via ultralytics .track()
- Assigns visitor_id per track session
- Detects staff: anyone visible in first 30 seconds of footage
- Emits structured events: ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY
- Writes output to data/events.jsonl

### pipeline/emit.py
- Reads events.jsonl and POSTs to /events/ingest in batches of 100
- Idempotent: safe to run multiple times

### app/ingestion.py
- Validates events with Pydantic
- Deduplicates by event_id (idempotent)
- Partial success: accepts valid events even if some are malformed

### app/metrics.py
- Computes unique_visitors, conversion_rate, avg_dwell_per_zone,
  queue_depth, abandonment_rate in real time from SQLite

### app/funnel.py
- Session-based funnel: Entry → Zone Visit → Billing Queue → Purchase
- Re-entries do not double-count visitors

### app/anomalies.py
- BILLING_QUEUE_SPIKE: queue depth >= 5 (WARN) or >= 10 (CRITICAL)
- CONVERSION_DROP: rate below 20% with >= 5 visitors (WARN)
- DEAD_ZONE: no zone visits in last 30 minutes (INFO)

## AI-Assisted Decisions

### 1. Staff detection approach
I asked Claude to suggest approaches for staff detection without a
labelled dataset. It suggested OSNet Re-ID with a staff gallery, full
pose estimation, and a simple heuristic (first-frame appearance).
I chose the heuristic approach — anyone visible in the first 30 seconds
of footage is likely staff opening the store. This trades accuracy for
zero setup cost. OSNet would require a labelled staff gallery we don't
have. For production, I would collect 20-30 staff images and use
torchreid for proper Re-ID.

### 2. Event schema design
Claude suggested splitting events into separate tables (entries, zone_events,
billing_events) for query performance. I disagreed — a single events table
with an event_type column is simpler to ingest and query at our data volumes
(~400 events/day per store). The tradeoff: slightly heavier JOIN queries for
funnel, but dramatically simpler ingest path and schema evolution.

### 3. Re-entry detection
Claude suggested using appearance embeddings (OSNet) to match re-entering
visitors. I chose a time-window heuristic instead: same visitor_id + exit
followed by entry within 10 minutes = REENTRY. This is less accurate for
long re-entries but covers the most common case (stepping outside briefly)
without requiring a Re-ID model.

## Known Limitations

- Staff detection fails if staff arrive after the first 30 seconds
- Direction-based entry/exit uses first-appearance heuristic, not true
  crossing detection — may overcount in busy entry periods
- Camera overlap deduplication is not implemented — same person on
  floor and entry camera may generate duplicate visitor_ids
- SQLite write contention at high ingest rates (>100 events/sec) —
  use PostgreSQL with WAL mode for production
