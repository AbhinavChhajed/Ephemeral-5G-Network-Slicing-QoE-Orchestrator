import React, { useState, useEffect } from "react";
import "../styles/SystemStatus.css";

/**
 * SystemStatus Component
 *
 * Displays system health and configuration:
 * - Backend service status
 * - Ryu controller connectivity
 * - Network configuration
 * - API endpoints
 */
function SystemStatus() {
  const [status, setStatus] = useState(null);
  const [health, setHealth] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  /**
   * Fetch system status and health
   */
  const fetchStatus = async () => {
    try {
      const [statusRes, healthRes] = await Promise.all([
        fetch("http://localhost:8000/status"),
        fetch("http://localhost:8000/health"),
      ]);

      if (!statusRes.ok || !healthRes.ok) {
        throw new Error("Failed to fetch status");
      }

      const statusData = await statusRes.json();
      const healthData = await healthRes.json();

      setStatus(statusData);
      setHealth(healthData);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error("Status fetch error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    // Refresh every 10 seconds
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case "healthy":
      case "connected":
        return "#10b981";
      case "degraded":
        return "#f59e0b";
      case "unhealthy":
      case "disconnected":
        return "#ef4444";
      default:
        return "#6b7280";
    }
  };

  return (
    <div className="system-status-container">
      <div className="status-header">
        <h2>System Status & Configuration</h2>
        <button className="refresh-btn" onClick={fetchStatus}>
          🔄 Refresh
        </button>
      </div>

      {error && <div className="error-banner">⚠️ Error: {error}</div>}

      {isLoading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading system status...</p>
        </div>
      ) : (
        <>
          {/* Health Summary */}
          {health && (
            <div className="status-section">
              <h3>Service Health</h3>
              <div className="status-grid">
                <div className="status-item">
                  <label>Overall Status:</label>
                  <div
                    className="status-value"
                    style={{ color: getStatusColor(health.status) }}
                  >
                    {health.status.toUpperCase()}
                  </div>
                </div>

                <div className="status-item">
                  <label>Uptime:</label>
                  <div className="status-value">
                    {(health.uptime_seconds / 60).toFixed(1)} minutes
                  </div>
                </div>

                <div className="status-item">
                  <label>API Version:</label>
                  <div className="status-value">{health.version}</div>
                </div>

                <div className="status-item">
                  <label>Active Slices:</label>
                  <div className="status-value">{health.active_slices}</div>
                </div>
              </div>

              {/* Component Health */}
              <div className="components-health">
                <h4>Component Status:</h4>
                <div className="components-list">
                  {Object.entries(health.components || {}).map(
                    ([component, status]) => (
                      <div key={component} className="component-item">
                        <div
                          className="component-indicator"
                          style={{ backgroundColor: getStatusColor(status) }}
                        ></div>
                        <span className="component-name">{component}</span>
                        <span className="component-status">
                          {status.toUpperCase()}
                        </span>
                      </div>
                    ),
                  )}
                </div>
              </div>
            </div>
          )}

          {/* System Configuration */}
          {status && (
            <div className="status-section">
              <h3>System Configuration</h3>
              <div className="config-grid">
                <div className="config-item">
                  <label>Service Name:</label>
                  <span>{status.service}</span>
                </div>

                <div className="config-item">
                  <label>Service Status:</label>
                  <span>{status.status}</span>
                </div>

                <div className="config-item">
                  <label>Ryu Controller:</label>
                  <span>{status.ryu_controller}</span>
                </div>

                <div className="config-item">
                  <label>Controller Connected:</label>
                  <span
                    style={{
                      color: getStatusColor(
                        status.ryu_connected ? "connected" : "disconnected",
                      ),
                    }}
                  >
                    {status.ryu_connected ? "✓ Connected" : "✗ Disconnected"}
                  </span>
                </div>
              </div>

              {/* Slices Stats */}
              <div className="stats-section">
                <h4>Slices Statistics:</h4>
                <div className="stats-grid">
                  <div className="stat-card">
                    <div className="stat-label">Total Slices</div>
                    <div className="stat-value">
                      {status.slices?.total || 0}
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Active Slices</div>
                    <div className="stat-value">
                      {status.slices?.active || 0}
                    </div>
                  </div>
                </div>
              </div>

              {/* Telemetry Stats */}
              <div className="stats-section">
                <h4>Telemetry Statistics:</h4>
                <div className="stats-grid">
                  <div className="stat-card">
                    <div className="stat-label">Buffer Size</div>
                    <div className="stat-value">
                      {status.telemetry?.buffer_size || 0}
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">QoE History</div>
                    <div className="stat-value">
                      {status.telemetry?.qoe_history_size || 0}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* API Endpoints */}
          <div className="status-section">
            <h3>API Documentation</h3>
            <div className="endpoints-list">
              <div className="endpoint-group">
                <h4>Slices</h4>
                <ul>
                  <li>
                    <code>POST /api/slices/create_slice</code> - Create slice
                  </li>
                  <li>
                    <code>GET /api/slices/</code> - List slices
                  </li>
                  <li>
                    <code>GET /api/slices/{"{id}"}</code> - Get slice details
                  </li>
                  <li>
                    <code>PATCH /api/slices/{"{id}"}</code> - Modify slice
                  </li>
                  <li>
                    <code>DELETE /api/slices/{"{id}"}</code> - Delete slice
                  </li>
                </ul>
              </div>

              <div className="endpoint-group">
                <h4>Telemetry</h4>
                <ul>
                  <li>
                    <code>POST /api/telemetry/ingest</code> - Ingest metrics
                  </li>
                  <li>
                    <code>GET /api/telemetry/latest</code> - Latest snapshot
                  </li>
                  <li>
                    <code>GET /api/telemetry/qoe/{"{id}"}</code> - QoE score
                  </li>
                  <li>
                    <code>GET /api/telemetry/history</code> - QoE history
                  </li>
                </ul>
              </div>

              <div className="endpoint-group">
                <h4>WebSocket</h4>
                <ul>
                  <li>
                    <code>WS /ws/telemetry</code> - Live telemetry stream
                  </li>
                </ul>
              </div>
            </div>

            <div className="api-link">
              <p>📖 Full API documentation:</p>
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noopener noreferrer"
              >
                http://localhost:8000/docs (OpenAPI/Swagger)
              </a>
            </div>
          </div>

          {/* Environment Info */}
          <div className="status-section environment-info">
            <h3>Environment</h3>
            <div className="env-details">
              <div className="env-item">
                <label>Backend URL:</label>
                <code>http://localhost:8000</code>
              </div>
              <div className="env-item">
                <label>Frontend URL:</label>
                <code>http://localhost:3000</code>
              </div>
              <div className="env-item">
                <label>Network Controller:</label>
                <code>Ryu SDN Controller @ localhost:6633</code>
              </div>
              <div className="env-item">
                <label>Mininet Topology:</label>
                <code>1 switch + 3 hosts (video, gaming, iot)</code>
              </div>
              <div className="env-item">
                <label>Orchestrator:</label>
                <code>LangGraph with Ollama/GPT-4 LLM</code>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default SystemStatus;
