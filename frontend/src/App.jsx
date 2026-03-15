import React, { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import "./App.css";
import "./styles/Dashboard.css";
import "./styles/NetworkGraph.css";
import "./styles/AgentLogs.css";
import "./styles/SystemStatus.css";
import Dashboard from "./components/Dashboard";
import NetworkGraph from "./components/NetworkGraph";
import AgentLogs from "./components/AgentLogs";
import SystemStatus from "./components/SystemStatus";

/**
 * Main Application Component
 *
 * Provides layout, navigation, and component routing for the
 * 5G Network Slicing & QoE Orchestrator dashboard.
 */
function App() {
  const [systemHealth, setSystemHealth] = useState(null);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [isLoading, setIsLoading] = useState(true);

  // Fetch system health on mount
  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await fetch("http://localhost:8000/health");
        if (response.ok) {
          const data = await response.json();
          setSystemHealth(data);
        }
      } catch (error) {
        console.error("Failed to fetch health:", error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchHealth();
    // Refresh health every 10 seconds
    const interval = setInterval(fetchHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const healthStatus = systemHealth?.status || "unknown";
  const healthColor = {
    healthy: "bg-green-500",
    degraded: "bg-yellow-500",
    unhealthy: "bg-red-500",
    unknown: "bg-gray-500",
  }[healthStatus];

  return (
    <Router>
      <div className="app-container">
        {/* Header */}
        <header className="app-header">
          <div className="header-content">
            <div className="header-left">
              <h1 className="app-title">
                <span className="title-icon">⚡</span>
                5G Network Slicing & QoE Orchestrator
              </h1>
              <p className="app-subtitle">
                Real-time Network Orchestration Dashboard
              </p>
            </div>
            <div className="header-right">
              <div className={`health-indicator ${healthColor}`}>
                <span className="health-dot"></span>
                <span className="health-label">
                  {isLoading ? "Checking..." : healthStatus.toUpperCase()}
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Navigation */}
        <nav className="app-nav">
          <div className="nav-container">
            <button
              className={`nav-item ${activeTab === "dashboard" ? "active" : ""}`}
              onClick={() => setActiveTab("dashboard")}
            >
              <span className="nav-icon">📊</span>
              Dashboard
            </button>
            <button
              className={`nav-item ${activeTab === "metrics" ? "active" : ""}`}
              onClick={() => setActiveTab("metrics")}
            >
              <span className="nav-icon">📈</span>
              Network Metrics
            </button>
            <button
              className={`nav-item ${activeTab === "logs" ? "active" : ""}`}
              onClick={() => setActiveTab("logs")}
            >
              <span className="nav-icon">📝</span>
              Orchestrator Logs
            </button>
            <button
              className={`nav-item ${activeTab === "status" ? "active" : ""}`}
              onClick={() => setActiveTab("status")}
            >
              <span className="nav-icon">🔧</span>
              System Status
            </button>
          </div>
        </nav>

        {/* Main Content */}
        <main className="app-main">
          <div className="content-container">
            {activeTab === "dashboard" && <Dashboard />}
            {activeTab === "metrics" && <NetworkGraph />}
            {activeTab === "logs" && <AgentLogs />}
            {activeTab === "status" && <SystemStatus />}
          </div>
        </main>

        {/* Footer */}
        <footer className="app-footer">
          <div className="footer-content">
            <p>5G Network Slicing Orchestrator v1.0.0</p>
            <p className="api-status">
              Backend:{" "}
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noopener noreferrer"
              >
                http://localhost:8000
              </a>
            </p>
          </div>
        </footer>
      </div>
    </Router>
  );
}

export default App;
