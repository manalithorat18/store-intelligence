import json
import requests
import sys
from pathlib import Path

API_URL    = "http://127.0.0.1:8000"
EVENTS_FILE = "data/events.jsonl"
BATCH_SIZE  = 100


def feed_events():
    events_file = Path(EVENTS_FILE)
    if not events_file.exists():
        print(f"ERROR: {EVENTS_FILE} not found. Run detect.py first.")
        sys.exit(1)

    events = []
    with open(events_file) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    print(f"Loaded {len(events)} events from {EVENTS_FILE}")

    # Send in batches of 100
    total_accepted = 0
    total_rejected = 0

    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i:i + BATCH_SIZE]
        try:
            r = requests.post(
                f"{API_URL}/events/ingest",
                json={"events": batch},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                total_accepted += data["accepted"]
                total_rejected += data["rejected"]
                print(f"Batch {i//BATCH_SIZE + 1}: accepted={data['accepted']} rejected={data['rejected']}")
            else:
                print(f"Batch {i//BATCH_SIZE + 1}: HTTP {r.status_code} - {r.text[:200]}")
        except Exception as e:
            print(f"Batch {i//BATCH_SIZE + 1}: ERROR - {e}")

    print(f"\n✅ Done. Total accepted={total_accepted} rejected={total_rejected}")

    # Show metrics after ingestion
    print("\n── Store Metrics ──────────────────────────────")
    r = requests.get(f"{API_URL}/stores/STORE_BLR_002/metrics")
    print(json.dumps(r.json(), indent=2))

    print("\n── Funnel ─────────────────────────────────────")
    r = requests.get(f"{API_URL}/stores/STORE_BLR_002/funnel")
    print(json.dumps(r.json(), indent=2))

    print("\n── Anomalies ───────────────────────────────────")
    r = requests.get(f"{API_URL}/stores/STORE_BLR_002/anomalies")
    print(json.dumps(r.json(), indent=2))


if __name__ == "__main__":
    feed_events()