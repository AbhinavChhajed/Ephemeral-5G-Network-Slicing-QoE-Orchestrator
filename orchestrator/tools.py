"""
Tools for 5G Network Slicing AI Orchestrator
=============================================
Functions that enable LangGraph agents to interact with the FastAPI backend.
These tools allow:
- Fetching telemetry and QoE data
- Retrieving slice information
- Creating, modifying, and deleting slices
- Getting network status and statistics
"""

import httpx
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

LOG = logging.getLogger(__name__)

# Backend API configuration
BACKEND_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 10.0


class BackendAPIError(Exception):
    """Custom exception for backend API errors."""
    pass


async def fetch_with_retry(
    method: str,
    url: str,
    max_retries: int = 3,
    **kwargs
) -> Dict[str, Any]:
    """
    Make HTTP request with automatic retry logic.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        url: Full URL
        max_retries: Number of retry attempts
        **kwargs: Additional arguments for httpx
        
    Returns:
        Response JSON
        
    Raises:
        BackendAPIError: If request fails after retries
    """
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                if method == "GET":
                    response = await client.get(url, **kwargs)
                elif method == "POST":
                    response = await client.post(url, **kwargs)
                elif method == "PATCH":
                    response = await client.patch(url, **kwargs)
                elif method == "DELETE":
                    response = await client.delete(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                response.raise_for_status()
                return response.json() if response.text else {}
        
        except httpx.HTTPError as e:
            LOG.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # Wait before retry
            else:
                raise BackendAPIError(f"Request failed after {max_retries} attempts: {str(e)}")


async def get_latest_telemetry() -> Dict[str, Any]:
    """
    Fetch latest aggregated telemetry snapshot from backend.
    
    Returns:
        TelemetrySnapshot with current network metrics
        
    Raises:
        BackendAPIError: If API call fails
    """
    try:
        LOG.info("Fetching latest telemetry...")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/api/telemetry/latest"
        )
        LOG.info(f"Telemetry fetched: {len(result.get('slices', {}))} active slices")
        return result
    except Exception as e:
        LOG.error(f"Error fetching telemetry: {str(e)}")
        raise BackendAPIError(f"Failed to fetch telemetry: {str(e)}")


async def get_slice_info(slice_id: int) -> Dict[str, Any]:
    """
    Fetch information about a specific slice.
    
    Args:
        slice_id: ID of the slice
        
    Returns:
        SliceResponse with slice details
        
    Raises:
        BackendAPIError: If slice not found or API fails
    """
    try:
        LOG.info(f"Fetching slice info: {slice_id}")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/api/slices/{slice_id}"
        )
        return result
    except Exception as e:
        LOG.error(f"Error fetching slice {slice_id}: {str(e)}")
        raise BackendAPIError(f"Failed to fetch slice {slice_id}: {str(e)}")


async def list_all_slices() -> List[Dict[str, Any]]:
    """
    Fetch list of all slices.
    
    Returns:
        List of SliceResponse objects
        
    Raises:
        BackendAPIError: If API call fails
    """
    try:
        LOG.info("Fetching all slices...")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/api/slices/"
        )
        LOG.info(f"Retrieved {len(result)} slices")
        return result if isinstance(result, list) else [result]
    except Exception as e:
        LOG.error(f"Error listing slices: {str(e)}")
        raise BackendAPIError(f"Failed to list slices: {str(e)}")


async def get_qoe_score(slice_id: int, slice_type: str = "iot") -> Dict[str, Any]:
    """
    Calculate QoE score for a slice.
    
    Args:
        slice_id: ID of the slice
        slice_type: Type of slice (video, gaming, iot, voip)
        
    Returns:
        QoEScore with component breakdown
        
    Raises:
        BackendAPIError: If calculation fails
    """
    try:
        LOG.info(f"Calculating QoE for slice {slice_id} ({slice_type})...")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/api/telemetry/qoe/{slice_id}",
            params={"slice_type": slice_type}
        )
        return result
    except Exception as e:
        LOG.error(f"Error calculating QoE for slice {slice_id}: {str(e)}")
        raise BackendAPIError(f"Failed to calculate QoE: {str(e)}")


async def create_slice(
    slice_name: str,
    slice_type: str,
    priority: int,
    bandwidth_mbps: float,
    delay_ms: float,
    loss_percent: float,
    duration_minutes: Optional[int] = None,
    associated_hosts: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a new network slice.
    
    Args:
        slice_name: Human-readable name
        slice_type: Type (video, gaming, iot, voip, custom)
        priority: Priority level (1-100)
        bandwidth_mbps: Bandwidth allocation
        delay_ms: Maximum delay SLA
        loss_percent: Maximum loss SLA
        duration_minutes: Optional duration before auto-termination
        associated_hosts: Optional list of associated hosts
        metadata: Optional metadata dictionary
        
    Returns:
        SliceResponse with created slice details
        
    Raises:
        BackendAPIError: If creation fails
    """
    try:
        payload = {
            "slice_name": slice_name,
            "slice_type": slice_type,
            "priority": priority,
            "bandwidth_mbps": bandwidth_mbps,
            "delay_ms": delay_ms,
            "loss_percent": loss_percent,
        }
        if duration_minutes:
            payload["duration_minutes"] = duration_minutes
        if associated_hosts:
            payload["associated_hosts"] = associated_hosts
        if metadata:
            payload["metadata"] = metadata
        
        LOG.info(f"Creating slice: {slice_name} (type: {slice_type}, priority: {priority})")
        result = await fetch_with_retry(
            "POST",
            f"{BACKEND_URL}/api/slices/create_slice",
            json=payload
        )
        LOG.info(f"Slice created successfully: {result.get('slice_id')}")
        return result
    except Exception as e:
        LOG.error(f"Error creating slice: {str(e)}")
        raise BackendAPIError(f"Failed to create slice: {str(e)}")


async def modify_slice(
    slice_id: int,
    slice_name: Optional[str] = None,
    priority: Optional[int] = None,
    bandwidth_mbps: Optional[float] = None,
    delay_ms: Optional[float] = None,
    loss_percent: Optional[float] = None
) -> Dict[str, Any]:
    """
    Modify parameters of an existing slice.
    
    Args:
        slice_id: ID of slice to modify
        slice_name: New name (optional)
        priority: New priority (optional)
        bandwidth_mbps: New bandwidth (optional)
        delay_ms: New delay SLA (optional)
        loss_percent: New loss SLA (optional)
        
    Returns:
        Updated SliceResponse
        
    Raises:
        BackendAPIError: If modification fails
    """
    try:
        # Fetch current slice to preserve unspecified values
        current = await get_slice_info(slice_id)
        
        payload = {
            "slice_name": slice_name or current.get("slice_name"),
            "slice_type": current.get("slice_type", "custom"),
            "priority": priority if priority is not None else current.get("priority"),
            "bandwidth_mbps": bandwidth_mbps if bandwidth_mbps is not None else current.get("bandwidth_mbps"),
            "delay_ms": delay_ms if delay_ms is not None else current.get("delay_ms"),
            "loss_percent": loss_percent if loss_percent is not None else current.get("loss_percent"),
        }
        
        LOG.info(f"Modifying slice {slice_id}: {payload}")
        result = await fetch_with_retry(
            "PATCH",
            f"{BACKEND_URL}/api/slices/{slice_id}",
            json=payload
        )
        LOG.info(f"Slice {slice_id} modified successfully")
        return result
    except Exception as e:
        LOG.error(f"Error modifying slice {slice_id}: {str(e)}")
        raise BackendAPIError(f"Failed to modify slice: {str(e)}")


async def delete_slice(slice_id: int) -> Dict[str, Any]:
    """
    Terminate and delete a network slice.
    
    Args:
        slice_id: ID of slice to terminate
        
    Returns:
        ActionResponse confirming deletion
        
    Raises:
        BackendAPIError: If deletion fails
    """
    try:
        LOG.info(f"Deleting slice {slice_id}...")
        result = await fetch_with_retry(
            "DELETE",
            f"{BACKEND_URL}/api/slices/{slice_id}"
        )
        LOG.info(f"Slice {slice_id} deleted successfully")
        return result
    except Exception as e:
        LOG.error(f"Error deleting slice {slice_id}: {str(e)}")
        raise BackendAPIError(f"Failed to delete slice: {str(e)}")


async def get_slice_metrics(slice_id: int) -> Dict[str, Any]:
    """
    Get OpenFlow metrics for a slice.
    
    Args:
        slice_id: ID of the slice
        
    Returns:
        Dictionary with flow stats and meter stats
        
    Raises:
        BackendAPIError: If fetching fails
    """
    try:
        LOG.info(f"Fetching metrics for slice {slice_id}...")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/api/slices/{slice_id}/metrics"
        )
        return result
    except Exception as e:
        LOG.error(f"Error fetching metrics for slice {slice_id}: {str(e)}")
        raise BackendAPIError(f"Failed to fetch metrics: {str(e)}")


async def get_system_health() -> Dict[str, Any]:
    """
    Get system health status.
    
    Returns:
        HealthCheckResponse with component status
        
    Raises:
        BackendAPIError: If health check fails
    """
    try:
        LOG.info("Checking system health...")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/health"
        )
        return result
    except Exception as e:
        LOG.error(f"Error checking health: {str(e)}")
        raise BackendAPIError(f"Failed to check health: {str(e)}")


async def get_system_status() -> Dict[str, Any]:
    """
    Get detailed system status.
    
    Returns:
        System status with configuration and metrics
        
    Raises:
        BackendAPIError: If status call fails
    """
    try:
        LOG.info("Getting system status...")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/status"
        )
        return result
    except Exception as e:
        LOG.error(f"Error getting status: {str(e)}")
        raise BackendAPIError(f"Failed to get status: {str(e)}")


async def get_qoe_history(
    slice_id: Optional[int] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get QoE score history.
    
    Args:
        slice_id: Optional filter by slice
        limit: Maximum number of results
        
    Returns:
        List of QoEScore entries
        
    Raises:
        BackendAPIError: If retrieval fails
    """
    try:
        LOG.info(f"Fetching QoE history (limit: {limit})...")
        params = {"limit": limit}
        if slice_id is not None:
            params["slice_id"] = slice_id
        
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/api/telemetry/history",
            params=params
        )
        return result if isinstance(result, list) else [result]
    except Exception as e:
        LOG.error(f"Error fetching QoE history: {str(e)}")
        raise BackendAPIError(f"Failed to fetch history: {str(e)}")


async def get_telemetry_sources() -> Dict[str, Any]:
    """
    Get list of active telemetry sources.
    
    Returns:
        Dictionary with sources and their metrics
        
    Raises:
        BackendAPIError: If retrieval fails
    """
    try:
        LOG.info("Fetching telemetry sources...")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/api/telemetry/sources"
        )
        return result
    except Exception as e:
        LOG.error(f"Error fetching sources: {str(e)}")
        raise BackendAPIError(f"Failed to fetch sources: {str(e)}")


async def get_telemetry_stats() -> Dict[str, Any]:
    """
    Get telemetry buffer statistics.
    
    Returns:
        Dictionary with buffer stats
        
    Raises:
        BackendAPIError: If retrieval fails
    """
    try:
        LOG.info("Fetching telemetry statistics...")
        result = await fetch_with_retry(
            "GET",
            f"{BACKEND_URL}/api/telemetry/stats"
        )
        return result
    except Exception as e:
        LOG.error(f"Error fetching telemetry stats: {str(e)}")
        raise BackendAPIError(f"Failed to fetch stats: {str(e)}")


# Tool summary for LLM context
AVAILABLE_TOOLS = {
    "get_latest_telemetry": {
        "description": "Fetch latest aggregated telemetry snapshot from the network",
        "params": []
    },
    "get_slice_info": {
        "description": "Get detailed information about a specific slice",
        "params": [{"name": "slice_id", "type": "int"}]
    },
    "list_all_slices": {
        "description": "List all active slices in the network",
        "params": []
    },
    "get_qoe_score": {
        "description": "Calculate QoE score for a slice",
        "params": [
            {"name": "slice_id", "type": "int"},
            {"name": "slice_type", "type": "str", "default": "iot"}
        ]
    },
    "create_slice": {
        "description": "Create a new network slice with specified QoS parameters",
        "params": [
            {"name": "slice_name", "type": "str"},
            {"name": "slice_type", "type": "str"},
            {"name": "priority", "type": "int"},
            {"name": "bandwidth_mbps", "type": "float"},
            {"name": "delay_ms", "type": "float"},
            {"name": "loss_percent", "type": "float"},
            {"name": "duration_minutes", "type": "int", "optional": True},
            {"name": "associated_hosts", "type": "list", "optional": True},
            {"name": "metadata", "type": "dict", "optional": True}
        ]
    },
    "modify_slice": {
        "description": "Modify parameters of an existing slice",
        "params": [
            {"name": "slice_id", "type": "int"},
            {"name": "slice_name", "type": "str", "optional": True},
            {"name": "priority", "type": "int", "optional": True},
            {"name": "bandwidth_mbps", "type": "float", "optional": True},
            {"name": "delay_ms", "type": "float", "optional": True},
            {"name": "loss_percent", "type": "float", "optional": True}
        ]
    },
    "delete_slice": {
        "description": "Terminate and delete a network slice",
        "params": [{"name": "slice_id", "type": "int"}]
    },
    "get_slice_metrics": {
        "description": "Get OpenFlow metrics for a slice",
        "params": [{"name": "slice_id", "type": "int"}]
    },
    "get_system_health": {
        "description": "Get system health status",
        "params": []
    },
    "get_system_status": {
        "description": "Get detailed system status",
        "params": []
    },
    "get_qoe_history": {
        "description": "Get historical QoE scores",
        "params": [
            {"name": "slice_id", "type": "int", "optional": True},
            {"name": "limit", "type": "int", "default": 100}
        ]
    },
    "get_telemetry_sources": {
        "description": "Get list of active telemetry sources",
        "params": []
    },
    "get_telemetry_stats": {
        "description": "Get telemetry buffer statistics",
        "params": []
    }
}
