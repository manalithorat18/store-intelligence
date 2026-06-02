import cv2
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from ultralytics import YOLO

# ── Config ────────────────────────────────────────────────────────────────────

STORE_LAYOUT = "store_layout.json"
CLIPS_DIR    = "clips"
OUTPUT_FILE  = "data/events.jsonl"
CONFIDENCE   = 0.4
FRAME_SKIP   = 5

CAMERA_ZONE_MAP = {
    "entry_exit": "ENTRY_ZONE",
    "main_floor": "FOH",
    "billing":    "CASH_COUNTER",
}

# ── Load layout ───────────────────────────────────────────────────────────────

with open(STORE_LAYOUT) as f:
    layout = json.load(f)

STORE_ID = layout["store_id"]
CAMERAS  = {cam["camera_id"]: cam for cam in layout["cameras"]}

# ── Load YOLO ─────────────────────────────────────────────────────────────────

model = YOLO("yolov8n.pt")

# ── State ─────────────────────────────────────────────────────────────────────

sessions        = {}
visitor_history = {}
REENTRY_WINDOW  = 600


def get_or_create_session(track_id, camera_id):
    if track_id not in sessions:
        sessions[track_id] = {
            "visitor_id":      f"VIS_{uuid.uuid4().hex[:6]}",
            "camera_id":       camera_id,
            "session_seq":     0,
            "current_zone":    None,
            "dwell_start":     None,
            "last_dwell_emit": None,
            "is_staff":        False,
        }
    return sessions[track_id]


def next_seq(session):
    session["session_seq"] += 1
    return session["session_seq"]


def make_event(session, camera_id, event_type, timestamp,
               zone_id=None, dwell_ms=0, confidence=0.9, queue_depth=None):
    return {
        "event_id":   str(uuid.uuid4()),
        "store_id":   STORE_ID,
        "camera_id":  camera_id,
        "visitor_id": session["visitor_id"],
        "event_type": event_type,
        "timestamp":  timestamp,
        "zone_id":    zone_id,
        "dwell_ms":   dwell_ms,
        "is_staff":   session.get("is_staff", False),
        "confidence": round(confidence, 3),
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone":    None,
            "session_seq": next_seq(session),
        }
    }


# ── Process one clip ──────────────────────────────────────────────────────────

def process_clip(camera_id, video_path, clip_start_time, events_out):
    cam_info = CAMERAS[camera_id]
    cam_type = cam_info["type"]
    zone_id  = CAMERA_ZONE_MAP.get(cam_type, "FOH")

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15
    frame_num = 0

    prev_centroids       = {}
    staff_track_ids      = set()
    staff_detection_frames = fps * 30

    print(f"\n[{camera_id}] Processing {video_path.name} ...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_num += 1
        if frame_num % FRAME_SKIP != 0:
            continue

        offset_sec = frame_num / fps
        current_ts = (clip_start_time + timedelta(seconds=offset_sec))\
                     .strftime("%Y-%m-%dT%H:%M:%SZ")

        results = model.track(
            frame,
            persist=True,
            classes=[0],
            conf=CONFIDENCE,
            verbose=False
        )

        if results[0].boxes is None:
            continue

        boxes = results[0].boxes
        current_track_ids = set()

        for box in boxes:
            if box.id is None:
                continue

            track_id   = int(box.id.item())
            conf_score = float(box.conf.item())
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2

            current_track_ids.add(track_id)
            session = get_or_create_session(track_id, camera_id)

            # Staff detection: anyone visible in first 30s = staff
            if frame_num <= staff_detection_frames:
                staff_track_ids.add(track_id)
                session["is_staff"] = True
            else:
                session["is_staff"] = track_id in staff_track_ids

            if session["is_staff"]:
                prev_centroids[track_id] = (cx, cy)
                continue

            # ── Entry camera ──────────────────────────────────────────────
            if cam_type == "entry_exit":
                visitor_id = session["visitor_id"]

                # First appearance = ENTRY
                if track_id not in prev_centroids:
                    if visitor_id in visitor_history:
                        last_exit = visitor_history[visitor_id].get("exit_time")
                        if last_exit:
                            gap = (clip_start_time + timedelta(seconds=offset_sec) - last_exit).total_seconds()
                            if gap < REENTRY_WINDOW:
                                events_out.append(make_event(
                                    session, camera_id, "REENTRY",
                                    current_ts, confidence=conf_score
                                ))
                                prev_centroids[track_id] = (cx, cy)
                                continue

                    events_out.append(make_event(
                        session, camera_id, "ENTRY",
                        current_ts, confidence=conf_score
                    ))
                    visitor_history[visitor_id] = {
                        "entry_time": clip_start_time + timedelta(seconds=offset_sec)
                    }

            # ── Floor / billing cameras ───────────────────────────────────
            else:
                current_zone = zone_id

                if session["current_zone"] != current_zone:
                    if session["current_zone"]:
                        events_out.append(make_event(
                            session, camera_id, "ZONE_EXIT",
                            current_ts,
                            zone_id=session["current_zone"],
                            confidence=conf_score
                        ))

                    session["current_zone"]    = current_zone
                    session["dwell_start"]     = offset_sec
                    session["last_dwell_emit"] = offset_sec

                    if cam_type == "billing":
                        queue_depth = len([
                            t for t in current_track_ids
                            if not sessions.get(t, {}).get("is_staff", False)
                        ])
                        events_out.append(make_event(
                            session, camera_id, "BILLING_QUEUE_JOIN",
                            current_ts,
                            zone_id=current_zone,
                            confidence=conf_score,
                            queue_depth=queue_depth
                        ))
                    else:
                        events_out.append(make_event(
                            session, camera_id, "ZONE_ENTER",
                            current_ts,
                            zone_id=current_zone,
                            confidence=conf_score
                        ))

                elif session["dwell_start"] is not None:
                    dwell_elapsed = offset_sec - session["last_dwell_emit"]
                    if dwell_elapsed >= 30:
                        total_dwell = int((offset_sec - session["dwell_start"]) * 1000)
                        events_out.append(make_event(
                            session, camera_id, "ZONE_DWELL",
                            current_ts,
                            zone_id=current_zone,
                            dwell_ms=total_dwell,
                            confidence=conf_score
                        ))
                        session["last_dwell_emit"] = offset_sec

            prev_centroids[track_id] = (cx, cy)

        # ── Disappearance = EXIT ──────────────────────────────────────────
        disappeared = set(prev_centroids.keys()) - current_track_ids

        if cam_type == "entry_exit":
            for track_id in disappeared:
                if track_id in sessions:
                    session = sessions[track_id]
                    if not session.get("is_staff"):
                        visitor_id = session["visitor_id"]
                        events_out.append(make_event(
                            session, camera_id, "EXIT",
                            current_ts, confidence=0.7
                        ))
                        if visitor_id not in visitor_history:
                            visitor_history[visitor_id] = {}
                        visitor_history[visitor_id]["exit_time"] = (
                            clip_start_time + timedelta(seconds=offset_sec)
                        )
                if track_id in prev_centroids:
                    del prev_centroids[track_id]
        else:
            for track_id in disappeared:
                if track_id in sessions:
                    session = sessions[track_id]
                    if session.get("current_zone") and not session.get("is_staff"):
                        if cam_type == "billing":
                            events_out.append(make_event(
                                session, camera_id, "BILLING_QUEUE_ABANDON",
                                current_ts,
                                zone_id=session["current_zone"],
                                confidence=0.7
                            ))
                        else:
                            events_out.append(make_event(
                                session, camera_id, "ZONE_EXIT",
                                current_ts,
                                zone_id=session["current_zone"],
                                confidence=0.7
                            ))
                        session["current_zone"] = None
                if track_id in prev_centroids:
                    del prev_centroids[track_id]

    cap.release()
    print(f"[{camera_id}] Done. Events so far: {len(events_out)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    Path("data").mkdir(exist_ok=True)
    events = []

    clip_start = datetime(2026, 4, 10, 10, 0, 0)

    camera_files = [
        ("CAM_ENTRY_01",   "CAM 1.mp4"),
        ("CAM_FLOOR_01",   "CAM 2.mp4"),
        ("CAM_FLOOR_02",   "CAM 3.mp4"),
        ("CAM_FLOOR_03",   "CAM 4.mp4"),
        ("CAM_BILLING_01", "CAM 5.mp4"),
    ]

    for camera_id, filename in camera_files:
        video_path = Path(CLIPS_DIR) / filename
        if not video_path.exists():
            print(f"[SKIP] {filename} not found")
            continue
        process_clip(camera_id, video_path, clip_start, events)

    with open(OUTPUT_FILE, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    print(f"\n✅ Done. {len(events)} events written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()