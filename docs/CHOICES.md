# Engineering Decisions

## Decision 1 — Detection Model: YOLOv8n

### Options Considered
- **YOLOv8n** — lightweight, 6MB, ~40fps on CPU, mAP 37.3
- **YOLOv8s** — heavier, 22MB, ~18fps on CPU, mAP 44.9
- **MediaPipe Pose** — fast but pose-only, no bounding box tracking
- **GPT-4V / Claude Vision** — highly accurate but ~2s/frame latency

### What AI Suggested
I asked Claude to compare detection models for retail CCTV. It recommended
YOLOv8s for better accuracy on partially occluded people (common in retail).
It also suggested using a VLM for staff detection via uniform classification.

### What I Chose and Why
I chose YOLOv8n over YOLOv8s. Our videos are 15fps and we skip every 5th
frame — at that rate, YOLOv8n processes frames fast enough to stay real-time
on CPU without a GPU. The mAP tradeoff (37.3 vs 44.9) is acceptable because
we are counting people, not identifying fine-grained attributes. For the
staff detection, I rejected the VLM approach — 2s/frame would make a 20-minute
clip take 24 hours to process. Instead I used a first-30-seconds heuristic:
anyone visible at store opening is staff. This works well for this dataset
where staff are present before customers arrive.

---

## Decision 2 — Event Schema Design

### Options Considered
- **Single events table** — all event types in one table, event_type column
- **Separate tables** — entries table, zone_events table, billing_events table
- **Time-series store (TimescaleDB)** — optimised for time-range queries

### What AI Suggested
Claude suggested separate tables for better query performance and cleaner
schema design. It argued that JOINs across event types would be slow at scale.

### What I Chose and Why
I disagreed with the AI and chose a single events table. At our data volumes
— ~400 events per store per day across 40 stores — that is 16,000 rows/day,
well within SQLite's comfort zone. A single table means simpler ingest code,
simpler Pydantic validation, and easier schema evolution. If a new event type
is added, no migration is needed. The query performance concern is valid at
millions of rows but premature at our current scale. I added indexes on
store_id, event_type, visitor_id, and timestamp to mitigate query cost.

---

## Decision 3 — API Storage Engine

### Options Considered
- **SQLite** — zero setup, file-based, ships inside the container
- **PostgreSQL** — production-grade, handles concurrency, needs separate service
- **Redis** — fast for counters but not queryable for funnel analysis

### What AI Suggested
Claude recommended PostgreSQL with TimescaleDB extension for time-series
metrics, arguing it would handle concurrent ingest from 40 stores more
reliably than SQLite.

### What I Chose and Why
I chose SQLite with WAL (Write-Ahead Logging) mode for this prototype.
The challenge spec says the API must run via docker compose up with no
manual steps — SQLite requires zero infrastructure, making the acceptance
gate trivially easy to pass. PostgreSQL adds a second container, environment
variables, health check dependencies, and migration tooling. For a 48-hour
challenge with one store in scope, that complexity is not justified.

The honest tradeoff: SQLite will struggle with concurrent writes above
~100 requests/second. At 40 live stores each sending 500-event batches
every few minutes, the first thing that breaks is ingest latency under
contention. My mitigation is WAL mode (concurrent reads don't block writes)
and batched ingest (reduces connection overhead). For production, I would
switch to PostgreSQL with a connection pool.

I disagreed with the AI here — it was optimising for scale I don't have yet.