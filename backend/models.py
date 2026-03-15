"""
Pydantic Models for 5G Network Slicing Backend
===============================================
Defines data schemas for:
- Slice creation and management requests
- Telemetry data ingestion
- Controller actions and responses
- QoE metrics
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class SliceType(str, Enum):
    """Enumeration of network slice types."""
    VIDEO = "video"
    GAMING = "gaming"
    IOT = "iot"
    VOIP = "voip"
    CUSTOM = "custom"


class SliceStatus(str, Enum):
    """Enumeration of slice lifecycle states."""
    PENDING = "pending"
    ACTIVE = "active"
    MODIFYING = "modifying"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"


class ActionType(str, Enum):
    """Enumeration of orchestrator actions."""
    CREATE = "create"
    MODIFY = "modify"
    DESTROY = "destroy"
    MONITOR = "monitor"


class SliceRequest(BaseModel):
    """
    Request model for creating or modifying a network slice.
    """
    slice_name: str = Field(..., min_length=1, max_length=255, description="Human-readable slice name")
    slice_type: SliceType = Field(..., description="Type of slice (video, gaming, iot, voip, custom)")
    priority: int = Field(..., ge=1, le=100, description="Priority level (1-100, higher = better)")
    bandwidth_mbps: float = Field(..., gt=0, le=1000, description="Bandwidth allocation in Mbps")
    delay_ms: float = Field(..., ge=0, le=1000, description="Maximum acceptable delay in ms")
    loss_percent: float = Field(..., ge=0, le=100, description="Maximum acceptable packet loss %")
    duration_minutes: Optional[int] = Field(None, ge=1, le=1440, description="Slice duration in minutes (optional)")
    associated_hosts: Optional[List[str]] = Field(None, description="Associated host identifiers (h1, h2, h3)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    @validator('bandwidth_mbps')
    def validate_bandwidth(cls, v):
        """Ensure bandwidth is realistic."""
        if v < 0.1:
            raise ValueError("Bandwidth must be at least 0.1 Mbps")
        return v

    @validator('loss_percent')
    def validate_loss(cls, v):
        """Ensure loss percentage is valid."""
        if v > 50:
            raise ValueError("Loss percentage cannot exceed 50%")
        return v

    class Config:
        description = "Network slice creation request"
        example = {
            "slice_name": "Gaming Slice 1",
            "slice_type": "gaming",
            "priority": 80,
            "bandwidth_mbps": 50,
            "delay_ms": 5,
            "loss_percent": 0.05,
            "duration_minutes": 60,
            "associated_hosts": ["h2", "h3"]
        }


class SliceResponse(BaseModel):
    """
    Response model for slice creation/modification.
    """
    slice_id: int = Field(..., description="Unique slice identifier")
    slice_name: str = Field(..., description="Slice name")
    slice_type: SliceType = Field(..., description="Type of slice")
    status: SliceStatus = Field(..., description="Current slice status")
    priority: int = Field(..., description="Slice priority")
    bandwidth_mbps: float = Field(..., description="Allocated bandwidth")
    delay_ms: float = Field(..., description="Current delay SLA")
    loss_percent: float = Field(..., description="Current loss SLA")
    created_at: datetime = Field(..., description="Slice creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    expires_at: Optional[datetime] = Field(None, description="Scheduled expiration time")
    meter_id: Optional[int] = Field(None, description="Associated OpenFlow meter ID")
    associated_hosts: List[str] = Field(default_factory=list, description="Associated hosts")

    class Config:
        description = "Network slice response"


class TelemetryDataPoint(BaseModel):
    """
    Single telemetry measurement.
    """
    timestamp: datetime = Field(..., description="Measurement timestamp")
    metric_name: str = Field(..., description="Metric name (latency, jitter, bandwidth, loss, etc)")
    value: float = Field(..., description="Metric value")
    unit: str = Field(..., description="Metric unit (ms, Mbps, %, etc)")
    source: str = Field(..., description="Measurement source (host, switch, interface)")
    associated_slice_id: Optional[int] = Field(None, description="Associated slice ID")
    labels: Optional[Dict[str, str]] = Field(None, description="Additional labels/tags")

    class Config:
        description = "Single telemetry data point"


class TelemetryData(BaseModel):
    """
    Batch telemetry data ingestion model.
    Allows submission of multiple metrics in one request.
    """
    slice_id: Optional[int] = Field(None, description="Associated slice ID")
    source_host: str = Field(..., description="Source host identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Batch timestamp")
    metrics: Dict[str, float] = Field(..., description="Dictionary of metric_name: value")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional context")

    class Config:
        description = "Telemetry data batch ingestion"
        example = {
            "slice_id": 1,
            "source_host": "h1",
            "timestamp": "2026-03-15T10:30:00Z",
            "metrics": {
                "latency_ms": 12.5,
                "jitter_ms": 2.1,
                "bandwidth_mbps": 95.5,
                "packet_loss_percent": 0.05,
                "cpu_usage_percent": 45.2,
                "memory_usage_percent": 62.0
            },
            "metadata": {
                "interface": "eth0",
                "direction": "inbound"
            }
        }


class TelemetrySnapshot(BaseModel):
    """
    Current snapshot of network telemetry state.
    Represents the most recent measurements across all slices.
    """
    timestamp: datetime = Field(..., description="Snapshot timestamp")
    slices: Dict[int, Dict[str, float]] = Field(..., description="Per-slice metrics")
    global_metrics: Dict[str, float] = Field(..., description="Network-wide metrics")
    active_slice_count: int = Field(..., description="Number of active slices")
    total_bandwidth_used_mbps: float = Field(..., description="Total bandwidth utilization")

    class Config:
        description = "Network telemetry snapshot"


class QoEScore(BaseModel):
    """
    Quality of Experience score calculation result.
    """
    slice_id: int = Field(..., description="Associated slice ID")
    score: float = Field(..., ge=0, le=100, description="QoE score (0-100)")
    latency_impact: float = Field(..., description="Latency contribution to QoE")
    bandwidth_impact: float = Field(..., description="Bandwidth contribution to QoE")
    loss_impact: float = Field(..., description="Loss contribution to QoE")
    jitter_impact: float = Field(..., description="Jitter contribution to QoE")
    status: str = Field(..., description="Status (excellent, good, fair, poor)")
    timestamp: datetime = Field(..., description="Calculation timestamp")
    recommendations: List[str] = Field(default_factory=list, description="Improvement recommendations")

    class Config:
        description = "QoE score with component breakdown"


class ActionResponse(BaseModel):
    """
    Response model for orchestrator actions.
    Indicates whether an action was executed successfully.
    """
    action_id: str = Field(..., description="Unique action identifier")
    action_type: ActionType = Field(..., description="Type of action executed")
    target_slice_id: Optional[int] = Field(None, description="Target slice ID")
    status: str = Field(..., description="Action status (success, pending, failed)")
    message: str = Field(..., description="Action feedback message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Action timestamp")
    executed_at: Optional[datetime] = Field(None, description="Execution completion time")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        description = "Orchestrator action response"


class HealthCheckResponse(BaseModel):
    """
    Health check status for the backend service.
    """
    status: str = Field(..., description="Service status (healthy, degraded, unhealthy)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")
    version: str = Field(..., description="Backend version")
    components: Dict[str, str] = Field(..., description="Component health status")
    active_slices: int = Field(..., description="Number of active slices")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")

    class Config:
        description = "Service health status"


class ErrorResponse(BaseModel):
    """
    Standard error response model.
    """
    error: str = Field(..., description="Error message")
    status_code: int = Field(..., ge=400, le=599, description="HTTP status code")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Unique request identifier for tracing")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

    class Config:
        description = "Standard error response"


class ControllerStats(BaseModel):
    """
    Current Ryu controller statistics.
    """
    connected_datapaths: int = Field(..., description="Number of connected datapaths")
    total_slices: int = Field(..., description="Total slices created")
    active_slices: int = Field(..., description="Active slices")
    total_flows: int = Field(..., description="Total flow entries")
    total_meters: int = Field(..., description="Total meters installed")
    datapaths: List[str] = Field(..., description="Connected datapath IDs")
    last_update: datetime = Field(..., description="Last stats update")

    class Config:
        description = "Ryu controller statistics"


class NetworkStateResponse(BaseModel):
    """
    Complete network state snapshot.
    Includes slices, telemetry, and controller stats.
    """
    timestamp: datetime = Field(..., description="State snapshot timestamp")
    slices: List[SliceResponse] = Field(..., description="All slice details")
    telemetry: TelemetrySnapshot = Field(..., description="Telemetry snapshot")
    controller_stats: ControllerStats = Field(..., description="Controller statistics")
    qoe_scores: List[QoEScore] = Field(..., description="QoE scores for active slices")

    class Config:
        description = "Complete network state"
