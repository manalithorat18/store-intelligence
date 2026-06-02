# Store Intelligence API

End-to-end CCTV analytics pipeline for Apex Retail — detects visitors, tracks behaviour, and exposes real-time store metrics via a REST API.

## Quick Start (5 commands)

```bash
git clone <your-repo-url>
cd store-intelligence
cp -r /path/to/clips ./clips
docker compose up --build
python pipeline/emit.py
```

## Running the Detection Pipeline

Place your .mp4 files in the `clips/` folder, then:

```bash
python pipeline/detect.py
```

This processes all 5 camera feeds and writes events to `data/events.jsonl`.

## Feeding Events into the API

```bash
python pipeline/emit.py
```

This reads `data/events.jsonl` and POSTs all events to the API in batches of 100.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| POST /events/ingest | Ingest up to 500 events |
| GET /stores/{id}/metrics | Unique visitors, conversion rate, dwell |
| GET /stores/{id}/funnel | Entry → Zone → Billing → Purchase |
| GET /stores/{id}/heatmap | Zone visit frequency normalised 0-100 |
| GET /stores/{id}/anomalies | Queue spikes, conversion drops, dead zones |
| GET /health | Service status and feed freshness |

## Running Tests

```bash
python -m pytest tests/ -v --cov=app --cov-report=term-missing
```

## Architecture
CCTV Clips → pipeline/detect.py (YOLOv8n + ByteTrack)
→ data/events.jsonl
→ pipeline/emit.py → POST /events/ingest
→ SQLite database
→ GET /stores/{id}/metrics|funnel|heatmap|anomalies

## North Star Metric

**Conversion Rate** = Visitors who reached billing ÷ Total unique visitors

Every component either improves accuracy of this number (detection layer)
or makes it actionable (API layer).

