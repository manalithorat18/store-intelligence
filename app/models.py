from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class EventType(str, Enum):
    ENTRY                 = "ENTRY"
    EXIT                  = "EXIT"
    ZONE_ENTER            = "ZONE_ENTER"
    ZONE_EXIT             = "ZONE_EXIT"
    ZONE_DWELL            = "ZONE_DWELL"
    BILLING_QUEUE_JOIN    = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY               = "REENTRY"


class EventMetadata(BaseModel):
    queue_depth: Optional[int]  = None
    sku_zone:    Optional[str]  = None
    session_seq: Optional[int]  = None


class Event(BaseModel):
    event_id:   str
    store_id:   str
    camera_id:  str
    visitor_id: str
    event_type: EventType
    timestamp:  str
    zone_id:    Optional[str]   = None
    dwell_ms:   int             = 0
    is_staff:   bool            = False
    confidence: float           = 1.0
    metadata:   EventMetadata   = Field(default_factory=EventMetadata)


class IngestRequest(BaseModel):
    events: List[Event]


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors:   List[str] = []


class ZoneDwell(BaseModel):
    zone_id:       str
    avg_dwell_ms:  float


class MetricsResponse(BaseModel):
    store_id:          str
    unique_visitors:   int
    conversion_rate:   float
    avg_dwell_per_zone: List[ZoneDwell]
    queue_depth:       int
    abandonment_rate:  float


class FunnelStage(BaseModel):
    stage:      str
    count:      int
    drop_off_pct: float


class FunnelResponse(BaseModel):
    store_id: str
    stages:   List[FunnelStage]


class HeatmapZone(BaseModel):
    zone_id:          str
    visit_frequency:  float
    avg_dwell_ms:     float
    normalised_score: float
    data_confidence:  str


class HeatmapResponse(BaseModel):
    store_id: str
    zones:    List[HeatmapZone]


class Anomaly(BaseModel):
    anomaly_type:     str
    severity:         str
    description:      str
    suggested_action: str


class AnomalyResponse(BaseModel):
    store_id:  str
    anomalies: List[Anomaly]


class HealthResponse(BaseModel):
    status:               str
    last_event_timestamp: Optional[str]
    stale_feed:           bool