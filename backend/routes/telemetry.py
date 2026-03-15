"""
Telemetry Routes for 5G Network Slicing Backend
================================================
REST API endpoints for:
- Ingesting telemetry metrics (POST /ingest)
- Retrieving telemetry snapshots (GET /latest)
- QoE score calculations (GET /qoe/{slice_id})
- Historical telemetry queries (GET /history)
"""

from fastapi import APIRouter, HTTPException, Query, Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import json
from collections import defaultdict

from ..models import (
    TelemetryData,
    TelemetrySnapshot,
    QoEScore,
    ErrorResponse,
)

LOG = logging.getLogger(__name__)

# Create router for telemetry endpoints
router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

# In-memory telemetry storage (in production: use time-series database like InfluxDB)
telemetry_buffer: List[Dict] = []
latest_snapshot: Optional[TelemetrySnapshot] = None
qoe_history: List[QoEScore] = []

# Configuration
MAX_BUFFER_SIZE = 10000
QOE_CALCULATION_INTERVAL = 10  # seconds


class QoECalculator:
    """
    Calculates Quality of Experience scores based on telemetry metrics.
    Uses weighted scoring model:
    - Latency: 40% weight
    - Bandwidth: 30% weight
    - Packet Loss: 20% weight
    - Jitter: 10% weight
    """
    
    # Slice type SLA thresholds
    SLA_THRESHOLDS = {
        "video": {
            "latency_ms": 100,
            "bandwidth_mbps": 50,
            "loss_percent": 1.0,
            "jitter_ms": 10,
        },
        "gaming": {
            "latency_ms": 20,
            "bandwidth_mbps": 30,
            "loss_percent": 0.5,
            "jitter_ms": 5,
        },
        "iot": {
            "latency_ms": 500,
            "bandwidth_mbps": 10,
            "loss_percent": 5.0,
            "jitter_ms": 50,
        },
        "voip": {
            "latency_ms": 150,
            "bandwidth_mbps": 1,
            "loss_percent": 0.1,
            "jitter_ms": 30,
        },
    }
    
    # Weights for QoE components (sum = 1.0)
    WEIGHTS = {
        "latency": 0.40,
        "bandwidth": 0.30,
        "loss": 0.20,
        "jitter": 0.10,
    }
    
    @staticmethod
    def calculate_component_score(
        current_value: float,
        sla_threshold: float,
        inverted: bool = False
    ) -> float:
        """
        Calculate normalized score (0-100) for a single component.
        
        Args:
            current_value: Current metric value
            sla_threshold: SLA threshold
            inverted: If True, lower is better (loss, jitter); if False, higher is better
            
        Returns:
            Score from 0-100
        """
        if sla_threshold == 0:
            return 0
        
        if inverted:
            # Lower values are better (loss, jitter, latency)
            ratio = current_value / sla_threshold
        else:
            # Higher values are better (bandwidth)
            ratio = sla_threshold / current_value if current_value > 0 else 0
        
        # Score curve: 100% at SLA, degrading as deviation increases
        if ratio <= 0.5:
            return 100.0
        elif ratio <= 1.0:
            return 100.0
        elif ratio <= 2.0:
            return 100.0 - (ratio - 1.0) * 50
        else:
            return max(0, 50.0 - (ratio - 2.0) * 20)
    
    @staticmethod
    def calculate_qoe(
        slice_id: int,
        slice_type: str,
        latency_ms: float,
        bandwidth_mbps: float,
        loss_percent: float,
        jitter_ms: float,
    ) -> QoEScore:
        """
        Calculate comprehensive QoE score.
        
        Args:
            slice_id: Slice identifier
            slice_type: Type of slice
            latency_ms: Current latency in milliseconds
            bandwidth_mbps: Current bandwidth in Mbps
            loss_percent: Current packet loss percentage
            jitter_ms: Current jitter in milliseconds
            
        Returns:
            QoEScore with detailed component breakdown
        """
        sla = QoECalculator.SLA_THRESHOLDS.get(slice_type, QoECalculator.SLA_THRESHOLDS["iot"])
        
        # Calculate component scores
        latency_score = QoECalculator.calculate_component_score(
            latency_ms, sla["latency_ms"], inverted=True
        )
        bandwidth_score = QoECalculator.calculate_component_score(
            bandwidth_mbps, sla["bandwidth_mbps"], inverted=False
        )
        loss_score = QoECalculator.calculate_component_score(
            loss_percent, sla["loss_percent"], inverted=True
        )
        jitter_score = QoECalculator.calculate_component_score(
            jitter_ms, sla["jitter_ms"], inverted=True
        )
        
        # Calculate weighted QoE score
        weights = QoECalculator.WEIGHTS
        qoe_score = (
            latency_score * weights["latency"] +
            bandwidth_score * weights["bandwidth"] +
            loss_score * weights["loss"] +
            jitter_score * weights["jitter"]
        )
        
        # Determine status
        if qoe_score >= 80:
            status = "excellent"
        elif qoe_score >= 60:
            status = "good"
        elif qoe_score >= 40:
            status = "fair"
        else:
            status = "poor"
        
        # Generate recommendations
        recommendations = []
        if latency_score < 70:
            recommendations.append(f"Reduce latency: current {latency_ms}ms vs SLA {sla['latency_ms']}ms")
        if bandwidth_score < 70:
            recommendations.append(f"Increase bandwidth: current {bandwidth_mbps}Mbps vs SLA {sla['bandwidth_mbps']}Mbps")
        if loss_score < 70:
            recommendations.append(f"Reduce packet loss: current {loss_percent}% vs SLA {sla['loss_percent']}%")
        if jitter_score < 70:
            recommendations.append(f"Reduce jitter: current {jitter_ms}ms vs SLA {sla['jitter_ms']}ms")
        
        if not recommendations:
            recommendations.append("All QoE metrics within acceptable thresholds")
        
        return QoEScore(
            slice_id=slice_id,
            score=round(qoe_score, 2),
            latency_impact=latency_score,
            bandwidth_impact=bandwidth_score,
            loss_impact=loss_score,
            jitter_impact=jitter_score,
            status=status,
            timestamp=datetime.utcnow(),
            recommendations=recommendations
        )


@router.post("/ingest", response_model=Dict, status_code=202)
async def ingest_telemetry(telemetry: TelemetryData) -> Dict:
    """
    Ingest telemetry metrics from network sources.
    
    Accepts batch metrics from hosts, switches, or controllers.
    Stores in buffer for processing and aggregation.
    
    Args:
        telemetry: TelemetryData with metrics dictionary
        
    Returns:
        Acknowledgment response
    """
    global telemetry_buffer
    
    try:
        # Create unified telemetry entry
        entry = {
            "timestamp": telemetry.timestamp or datetime.utcnow(),
            "slice_id": telemetry.slice_id,
            "source_host": telemetry.source_host,
            "metrics": telemetry.metrics,
            "metadata": telemetry.metadata or {},
        }
        
        # Add to buffer
        telemetry_buffer.append(entry)
        
        # Maintain buffer size
        if len(telemetry_buffer) > MAX_BUFFER_SIZE:
            telemetry_buffer = telemetry_buffer[-MAX_BUFFER_SIZE:]
        
        LOG.info(f"Ingested telemetry from {telemetry.source_host}: {len(telemetry.metrics)} metrics")
        
        return {
            "status": "accepted",
            "message": f"Ingested {len(telemetry.metrics)} metrics",
            "buffer_size": len(telemetry_buffer),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        LOG.error(f"Error ingesting telemetry: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to ingest telemetry: {str(e)}"
        )


@router.get("/latest", response_model=TelemetrySnapshot)
async def get_latest_telemetry() -> TelemetrySnapshot:
    """
    Get the latest aggregated telemetry snapshot.
    
    Aggregates metrics from all recent entries to provide:
    - Per-slice metrics
    - Global network metrics
    - Active slice count
    - Total bandwidth utilization
    
    Returns:
        TelemetrySnapshot with current state
    """
    global telemetry_buffer, latest_snapshot
    
    try:
        # Aggregate metrics from recent buffer entries (last 5 minutes)
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)
        recent_entries = [e for e in telemetry_buffer if e["timestamp"] >= cutoff_time]
        
        # Organize by slice
        slice_metrics: Dict[int, Dict] = defaultdict(lambda: defaultdict(list))
        global_metrics: Dict[str, float] = defaultdict(float)
        
        for entry in recent_entries:
            slice_id = entry.get("slice_id", 0)
            for metric_name, value in entry["metrics"].items():
                slice_metrics[slice_id][metric_name].append(value)
                if metric_name == "bandwidth_mbps":
                    global_metrics["total_bandwidth_mbps"] += value
        
        # Average the values
        aggregate_slices = {}
        for slice_id, metrics in slice_metrics.items():
            aggregate_slices[slice_id] = {
                metric: sum(values) / len(values)
                for metric, values in metrics.items()
            }
        
        # Calculate derived metrics
        if recent_entries:
            global_metrics["average_latency_ms"] = sum(
                e["metrics"].get("latency_ms", 0) for e in recent_entries
            ) / len(recent_entries)
            global_metrics["average_loss_percent"] = sum(
                e["metrics"].get("packet_loss_percent", 0) for e in recent_entries
            ) / len(recent_entries)
        
        active_slices = len(aggregate_slices)
        total_bandwidth = global_metrics.get("total_bandwidth_mbps", 0)
        
        latest_snapshot = TelemetrySnapshot(
            timestamp=datetime.utcnow(),
            slices=aggregate_slices,
            global_metrics=dict(global_metrics),
            active_slice_count=active_slices,
            total_bandwidth_used_mbps=total_bandwidth
        )
        
        return latest_snapshot
        
    except Exception as e:
        LOG.error(f"Error retrieving telemetry: {str(e)}")
        # Return empty snapshot on error
        return TelemetrySnapshot(
            timestamp=datetime.utcnow(),
            slices={},
            global_metrics={},
            active_slice_count=0,
            total_bandwidth_used_mbps=0.0
        )


@router.get("/qoe/{slice_id}", response_model=QoEScore)
async def calculate_qoe(
    slice_id: int = Path(..., description="Slice ID", ge=0),
    slice_type: str = Query("iot", description="Slice type")
) -> QoEScore:
    """
    Calculate QoE score for a specific slice.
    
    Uses recent telemetry data and slice-type-specific SLA thresholds.
    
    Args:
        slice_id: Slice to calculate QoE for
        slice_type: Type of slice (video, gaming, iot, voip)
        
    Returns:
        QoEScore with component breakdown
    """
    try:
        # Get recent metrics for slice
        cutoff_time = datetime.utcnow() - timedelta(minutes=1)
        slice_entries = [
            e for e in telemetry_buffer
            if e.get("slice_id") == slice_id and e["timestamp"] >= cutoff_time
        ]
        
        if not slice_entries:
            # Return baseline poor score if no data
            return QoEScore(
                slice_id=slice_id,
                score=0.0,
                latency_impact=0.0,
                bandwidth_impact=0.0,
                loss_impact=0.0,
                jitter_impact=0.0,
                status="poor",
                timestamp=datetime.utcnow(),
                recommendations=["No recent telemetry data available"]
            )
        
        # Average the metrics
        avg_metrics = defaultdict(list)
        for entry in slice_entries:
            for metric, value in entry["metrics"].items():
                avg_metrics[metric].append(value)
        
        avg_values = {k: sum(v) / len(v) for k, v in avg_metrics.items()}
        
        # Calculate QoE
        qoe = QoECalculator.calculate_qoe(
            slice_id=slice_id,
            slice_type=slice_type,
            latency_ms=avg_values.get("latency_ms", 100),
            bandwidth_mbps=avg_values.get("bandwidth_mbps", 10),
            loss_percent=avg_values.get("packet_loss_percent", 1.0),
            jitter_ms=avg_values.get("jitter_ms", 20),
        )
        
        qoe_history.append(qoe)
        if len(qoe_history) > 1000:
            qoe_history.pop(0)
        
        return qoe
        
    except Exception as e:
        LOG.error(f"Error calculating QoE: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate QoE: {str(e)}"
        )


@router.get("/history", response_model=List[QoEScore])
async def get_qoe_history(
    slice_id: Optional[int] = Query(None, description="Filter by slice ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results")
) -> List[QoEScore]:
    """
    Retrieve QoE score history.
    
    Args:
        slice_id: Optional filter by slice
        limit: Maximum number of results
        
    Returns:
        List of QoEScore entries
    """
    try:
        history = qoe_history
        
        if slice_id is not None:
            history = [q for q in history if q.slice_id == slice_id]
        
        # Return most recent entries
        return history[-limit:]
        
    except Exception as e:
        LOG.error(f"Error retrieving QoE history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve history")


@router.get("/sources", response_model=Dict)
async def get_active_sources() -> Dict:
    """
    Get list of active telemetry sources.
    
    Returns:
        Dictionary with unique sources and their metrics
    """
    try:
        sources = defaultdict(set)
        
        for entry in telemetry_buffer[-1000:]:  # Look at recent entries
            source = entry.get("source_host", "unknown")
            for metric in entry.get("metrics", {}).keys():
                sources[source].add(metric)
        
        return {
            "active_sources": len(sources),
            "sources": {
                source: list(metrics)
                for source, metrics in sources.items()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        LOG.error(f"Error retrieving sources: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve sources")


@router.get("/stats", response_model=Dict)
async def get_telemetry_stats() -> Dict:
    """
    Get buffer statistics and storage info.
    
    Returns:
        Dictionary with telemetry statistics
    """
    try:
        cutoff_1m = datetime.utcnow() - timedelta(minutes=1)
        cutoff_5m = datetime.utcnow() - timedelta(minutes=5)
        cutoff_1h = datetime.utcnow() - timedelta(hours=1)
        
        entries_1m = len([e for e in telemetry_buffer if e["timestamp"] >= cutoff_1m])
        entries_5m = len([e for e in telemetry_buffer if e["timestamp"] >= cutoff_5m])
        entries_1h = len([e for e in telemetry_buffer if e["timestamp"] >= cutoff_1h])
        
        return {
            "total_entries": len(telemetry_buffer),
            "entries_last_1min": entries_1m,
            "entries_last_5min": entries_5m,
            "entries_last_1hour": entries_1h,
            "buffer_capacity": MAX_BUFFER_SIZE,
            "qoe_history_size": len(qoe_history),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        LOG.error(f"Error getting telemetry stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get stats")
