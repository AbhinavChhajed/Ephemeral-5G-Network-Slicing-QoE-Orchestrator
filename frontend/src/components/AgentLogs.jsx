import React, { useState, useEffect, useRef } from "react";
import "../styles/AgentLogs.css";

/**
 * AgentLogs Component
 *
 * Displays real-time feed of LangGraph orchestrator's:
 * - Reasoning and analysis
 * - Slice creation/modification/deletion decisions
 * - QoE scores and recommendations
 * - Execution results
 *
 * Connects via WebSocket for live updates (simulated with polling fallback).
 */
function AgentLogs() {
  const [logs, setLogs] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filterLevel, setFilterLevel] = useState("all");
  const [selectedLog, setSelectedLog] = useState(null);
  const logsEndRef = useRef(null);
  const wsRef = useRef(null);

  /**
   * Scroll to bottom of logs when new entries arrive
   */
  const scrollToBottom = () => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [logs, autoScroll]);

  /**
   * Connect to WebSocket or fallback to polling
   */
  useEffect(() => {
    const connectWebSocket = () => {
      try {
        wsRef.current = new WebSocket("ws://localhost:8000/ws/telemetry");

        wsRef.current.onopen = () => {
          setIsConnected(true);
          addLog("info", "WebSocket connected to orchestrator", {});
        };

        wsRef.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === "telemetry_snapshot") {
              // Simulated orchestrator log entry
              addLog("analysis", "Telemetry snapshot received", data.data);
            }
          } catch (error) {
            console.error("Error parsing WebSocket message:", error);
          }
        };

        wsRef.current.onerror = (error) => {
          console.error("WebSocket error:", error);
          setIsConnected(false);
        };

        wsRef.current.onclose = () => {
          setIsConnected(false);
          addLog("warning", "WebSocket disconnected", {});
          // Attempt reconnection in 5 seconds
          setTimeout(connectWebSocket, 5000);
        };
      } catch (error) {
        console.error("WebSocket connection failed:", error);
        setIsConnected(false);
        // Fallback to polling mode
        startPolling();
      }
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  /**
   * Fallback: Poll orchestrator decision history
   */
  const startPolling = () => {
    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(
          "http://localhost:8000/api/telemetry/history?limit=5",
        );
        if (response.ok) {
          const data = await response.json();
          data.forEach((qoe) => {
            addLog("analysis", `QoE Score: ${qoe.score} (${qoe.status})`, qoe);
          });
        }
      } catch (error) {
        console.error("Polling error:", error);
      }
    }, 10000); // Poll every 10 seconds

    return () => clearInterval(pollInterval);
  };

  /**
   * Add a new log entry
   */
  const addLog = (level, message, data = {}) => {
    const timestamp = new Date();
    const newLog = {
      id: Date.now() + Math.random(),
      timestamp,
      level,
      message,
      data,
    };

    setLogs((prev) => {
      const updated = [...prev, newLog];
      // Keep last 200 logs in memory
      if (updated.length > 200) {
        return updated.slice(-200);
      }
      return updated;
    });

    setIsLoading(false);
  };

  /**
   * Clear all logs
   */
  const clearLogs = () => {
    setLogs([]);
    setSelectedLog(null);
  };

  /**
   * Filter logs by level
   */
  const filteredLogs =
    filterLevel === "all"
      ? logs
      : logs.filter((log) => log.level === filterLevel);

  /**
   * Get log level styling
   */
  const getLevelColor = (level) => {
    switch (level) {
      case "error":
        return "error";
      case "warning":
        return "warning";
      case "info":
        return "info";
      case "analysis":
        return "analysis";
      case "decision":
        return "decision";
      case "execution":
        return "execution";
      default:
        return "default";
    }
  };

  /**
   * Format data object for display
   */
  const formatData = (data) => {
    if (!data || Object.keys(data).length === 0) return null;
    return JSON.stringify(data, null, 2);
  };

  return (
    <div className="agent-logs-container">
      <div className="logs-header">
        <h2>Orchestrator Decision Feed</h2>
        <div className="logs-controls">
          <div className="filter-group">
            <label>Filter:</label>
            <select
              value={filterLevel}
              onChange={(e) => setFilterLevel(e.target.value)}
            >
              <option value="all">All Levels</option>
              <option value="error">Errors</option>
              <option value="warning">Warnings</option>
              <option value="info">Info</option>
              <option value="analysis">Analysis</option>
              <option value="decision">Decisions</option>
              <option value="execution">Execution</option>
            </select>
          </div>

          <div className="connection-status">
            <span
              className={`status-indicator ${isConnected ? "connected" : "disconnected"}`}
            ></span>
            <span className="status-text">
              {isConnected ? "WebSocket Connected" : "Polling Mode"}
            </span>
          </div>

          <label className="auto-scroll-label">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>

          <button className="clear-btn" onClick={clearLogs}>
            🗑️ Clear
          </button>
        </div>
      </div>

      {isLoading && logs.length === 0 ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Waiting for orchestrator events...</p>
        </div>
      ) : (
        <div className="logs-content">
          <div className="logs-list">
            {filteredLogs.length === 0 ? (
              <div className="empty-state">
                <p>No logs to display</p>
              </div>
            ) : (
              filteredLogs.map((log) => (
                <div
                  key={log.id}
                  className={`log-entry ${getLevelColor(log.level)}`}
                  onClick={() =>
                    setSelectedLog(selectedLog?.id === log.id ? null : log)
                  }
                >
                  <div className="log-header">
                    <span className="log-time">
                      {log.timestamp.toLocaleTimeString()}
                    </span>
                    <span className="log-level-badge">
                      {log.level.toUpperCase()}
                    </span>
                    <span className="log-message">{log.message}</span>
                  </div>
                  {selectedLog?.id === log.id &&
                    log.data &&
                    Object.keys(log.data).length > 0 && (
                      <div className="log-details">
                        <pre>{formatData(log.data)}</pre>
                      </div>
                    )}
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>

          {/* Log Details Panel */}
          {selectedLog && (
            <div className="log-details-panel">
              <div className="details-header">
                <h3>Log Details</h3>
                <button
                  className="close-btn"
                  onClick={() => setSelectedLog(null)}
                >
                  ✕
                </button>
              </div>
              <div className="details-content">
                <div className="detail-item">
                  <label>Timestamp:</label>
                  <span>{selectedLog.timestamp.toLocaleString()}</span>
                </div>
                <div className="detail-item">
                  <label>Level:</label>
                  <span className={`badge ${getLevelColor(selectedLog.level)}`}>
                    {selectedLog.level.toUpperCase()}
                  </span>
                </div>
                <div className="detail-item">
                  <label>Message:</label>
                  <span>{selectedLog.message}</span>
                </div>
                {selectedLog.data &&
                  Object.keys(selectedLog.data).length > 0 && (
                    <div className="detail-item">
                      <label>Data:</label>
                      <pre>{formatData(selectedLog.data)}</pre>
                    </div>
                  )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      <div className="logs-legend">
        <h4>Log Levels:</h4>
        <div className="legend-items">
          <div className="legend-item">
            <span className="legend-color error"></span>
            <span>Error - Critical failures</span>
          </div>
          <div className="legend-item">
            <span className="legend-color warning"></span>
            <span>Warning - Potential issues</span>
          </div>
          <div className="legend-item">
            <span className="legend-color info"></span>
            <span>Info - General information</span>
          </div>
          <div className="legend-item">
            <span className="legend-color analysis"></span>
            <span>Analysis - QoE calculations</span>
          </div>
          <div className="legend-item">
            <span className="legend-color decision"></span>
            <span>Decision - Orchestration actions</span>
          </div>
          <div className="legend-item">
            <span className="legend-color execution"></span>
            <span>Execution - Network changes</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AgentLogs;
