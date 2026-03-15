"""
FastAPI Backend for 5G Network Slicing & QoE Orchestrator
==========================================================
Main application entry point with:
- FastAPI server setup
- CORS configuration
- Route registration
- Health checks
- Metrics exposure
- Websocket support for real-time telemetry
"""

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from datetime import datetime
import json
import asyncio
from typing import Dict, Any, Optional

# Import routes
from .routes import slicing, telemetry
from .models import HealthCheckResponse, NetworkStateResponse, ControllerStats, TelemetrySnapshot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)

# Application metadata
APP_VERSION = "1.0.0"
APP_NAME = "5G Network Slicing & QoE Orchestrator"
APP_DESCRIPTION = """
Ephemeral 5G Network Slicing with QoE-driven Orchestration

A comprehensive proof-of-concept system for dynamic creation, monitoring, and 
destruction of isolated virtual network slices based on real-time Quality of 
Experience telemetry using AI-powered orchestration.

**Core Capabilities:**
- Dynamic network slice creation and termination
- Real-time QoE monitoring and calculation
- AI-driven orchestration decisions
- OpenFlow-based network control
- Websocket support for live telemetry streaming
"""

# Track application startup/shutdown
app_state = {
    "startup_time": None,
    "is_ready": False,
    "ryu_controller_connected": False,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown events.
    """
    # Startup
    LOG.info(f"*** {APP_NAME} starting up (v{APP_VERSION}) ***")
    app_state["startup_time"] = datetime.utcnow()
    app_state["is_ready"] = True
    
    # Check Ryu controller availability
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get("http://127.0.0.1:8080/stats/switches")
            if response.status_code == 200:
                app_state["ryu_controller_connected"] = True
                LOG.info("*** Ryu controller connected ***")
            else:
                LOG.warning("Ryu controller not responding (may start later)")
    except Exception as e:
        LOG.warning(f"Ryu controller not available on startup: {str(e)}")
        LOG.info("Continuing in standalone mode; controller can be connected later")
    
    LOG.info("*** Backend API ready ***\n")
    
    yield
    
    # Shutdown
    LOG.info("\n*** Shutting down backend API ***")
    app_state["is_ready"] = False
    LOG.info("*** Backend shutdown complete ***")


# Create FastAPI application
app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Configure CORS (important for frontend access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # React dev server
        "http://127.0.0.1:3000",      # React dev server (localhost)
        "http://localhost:8080",      # Alternative
        "http://127.0.0.1:8080",      # Alternative
        "*"                            # Allow all (dev mode; restrict in production)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(slicing.router, prefix="/api")
app.include_router(telemetry.router, prefix="/api")


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["System"],
    summary="Health check endpoint"
)
async def health_check() -> HealthCheckResponse:
    """
    System health check.
    
    Returns:
        HealthCheckResponse with component status
    """
    uptime = 0.0
    if app_state["startup_time"]:
        uptime = (datetime.utcnow() - app_state["startup_time"]).total_seconds()
    
    status = "healthy" if app_state["is_ready"] else "unhealthy"
    
    return HealthCheckResponse(
        status=status,
        timestamp=datetime.utcnow(),
        version=APP_VERSION,
        components={
            "api_server": "healthy" if app_state["is_ready"] else "unhealthy",
            "ryu_controller": "connected" if app_state["ryu_controller_connected"] else "disconnected",
            "telemetry_buffer": "healthy",
            "slice_storage": "healthy",
        },
        active_slices=len(slicing.slice_store),
        uptime_seconds=uptime
    )


@app.get(
    "/status",
    response_model=Dict,
    tags=["System"],
    summary="Detailed system status"
)
async def system_status() -> Dict:
    """
    Get detailed system status including configuration.
    
    Returns:
        Dictionary with system information
    """
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "ready" if app_state["is_ready"] else "initializing",
        "uptime_seconds": (
            (datetime.utcnow() - app_state["startup_time"]).total_seconds()
            if app_state["startup_time"] else 0
        ),
        "ryu_controller": "http://127.0.0.1:8080",
        "ryu_connected": app_state["ryu_controller_connected"],
        "slices": {
            "total": len(slicing.slice_store),
            "active": sum(1 for s in slicing.slice_store.values() if s["status"] == "active")
        },
        "telemetry": {
            "buffer_size": len(telemetry.telemetry_buffer),
            "qoe_history_size": len(telemetry.qoe_history)
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get(
    "/info",
    response_model=Dict,
    tags=["System"],
    summary="API information and documentation"
)
async def api_info() -> Dict:
    """
    Get API information and available endpoints.
    
    Returns:
        Dictionary with API details
    """
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
        "endpoints": {
            "Slices": {
                "POST /api/slices/create_slice": "Create a new network slice",
                "GET /api/slices/": "List all slices",
                "GET /api/slices/{slice_id}": "Get slice details",
                "PATCH /api/slices/{slice_id}": "Modify slice parameters",
                "DELETE /api/slices/{slice_id}": "Terminate a slice",
                "GET /api/slices/{slice_id}/metrics": "Get slice metrics",
            },
            "Telemetry": {
                "POST /api/telemetry/ingest": "Ingest telemetry metrics",
                "GET /api/telemetry/latest": "Get latest telemetry snapshot",
                "GET /api/telemetry/qoe/{slice_id}": "Calculate QoE score",
                "GET /api/telemetry/history": "Get QoE history",
                "GET /api/telemetry/sources": "Get active telemetry sources",
                "GET /api/telemetry/stats": "Get telemetry statistics",
            },
            "System": {
                "GET /health": "Health check",
                "GET /status": "System status",
                "GET /info": "API information",
                "GET /docs": "OpenAPI documentation",
            }
        },
        "documentation": {
            "swagger_ui": "/docs",
            "openapi_schema": "/openapi.json",
        }
    }


# ============================================================================
# Websocket Endpoint for Real-time Telemetry Streaming
# ============================================================================

active_connections: list = []


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """
    Websocket endpoint for streaming real-time telemetry data.
    
    Clients can connect to receive live telemetry updates,
    including QoE scores and network metrics.
    """
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        LOG.info("New Websocket connection for telemetry streaming")
        
        while True:
            # Send telemetry snapshot every 2 seconds
            snapshot = await telemetry.get_latest_telemetry()
            
            await websocket.send_json({
                "type": "telemetry_snapshot",
                "data": snapshot.dict(),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            await asyncio.sleep(2)
            
    except Exception as e:
        LOG.warning(f"Websocket error: {str(e)}")
    finally:
        active_connections.remove(websocket)
        LOG.info("Websocket connection closed")


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Generic exception handler."""
    LOG.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ============================================================================
# Root Endpoint
# ============================================================================

@app.get("/", tags=["System"], summary="API root endpoint")
async def root() -> Dict:
    """
    Root endpoint providing basic service information.
    
    Returns:
        Service metadata and documentation links
    """
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "status_endpoint": "/status",
        "health_endpoint": "/health"
    }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    LOG.info(f"Starting {APP_NAME} v{APP_VERSION}")
    
    # Run with: python -m backend.main
    # Or: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
