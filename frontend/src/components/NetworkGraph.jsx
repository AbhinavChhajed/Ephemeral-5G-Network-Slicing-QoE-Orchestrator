import React, { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts";
import "../styles/NetworkGraph.css";

/**
 * NetworkGraph Component
 *
 * Displays real-time network metrics with live line charts:
 * - Latency trends over time
 * - Bandwidth utilization
 * - Packet loss percentage
 * - Jitter trends
 * - Active slices count
 *
 * Polls the FastAPI backend every 5 seconds for fresh telemetry.
 */
function NetworkGraph() {
  const [latencyData, setLatencyData] = useState([]);
  const [bandwidthData, setBandwidthData] = useState([]);
  const [sliceData, setSliceData] = useState([]);
  const [allMetricsData, setAllMetricsData] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdateTime, setLastUpdateTime] = useState(null);

  /**
   * Fetch telemetry data from backend
   */
  const fetchTelemetry = async () => {
    try {
      const response = await fetch(
        "http://localhost:8000/api/telemetry/latest",
      );
      if (!response.ok) throw new Error("Failed to fetch telemetry");

      const data = await response.json();
      const timestamp = new Date();

      // Extract and aggregate metrics
      const globalMetrics = data.global_metrics || {};
      const sliceCount = data.active_slice_count || 0;

      // Get average metrics for chart
      const avgLatency = globalMetrics.average_latency_ms || 0;
      const avgLoss = globalMetrics.average_loss_percent || 0;
      const totalBandwidth = globalMetrics.total_bandwidth_mbps || 0;

      // Update latency chart data
      setLatencyData((prev) => {
        const updated = [...prev];
        if (updated.length > 50) updated.shift(); // Keep last 50 data points
        updated.push({
          time: timestamp.toLocaleTimeString(),
          latency: parseFloat(avgLatency.toFixed(2)),
          loss: parseFloat(avgLoss.toFixed(3)),
        });
        return updated;
      });

      // Update bandwidth chart data
      setBandwidthData((prev) => {
        const updated = [...prev];
        if (updated.length > 50) updated.shift();
        updated.push({
          time: timestamp.toLocaleTimeString(),
          bandwidth: parseFloat(totalBandwidth.toFixed(2)),
        });
        return updated;
      });

      // Update slice count data
      setSliceData((prev) => {
        const updated = [...prev];
        if (updated.length > 50) updated.shift();
        updated.push({
          time: timestamp.toLocaleTimeString(),
          slices: sliceCount,
        });
        return updated;
      });

      // Update combined metrics
      setAllMetricsData((prev) => {
        const updated = [...prev];
        if (updated.length > 50) updated.shift();
        updated.push({
          time: timestamp.toLocaleTimeString(),
          latency: parseFloat(avgLatency.toFixed(2)),
          bandwidth: parseFloat(totalBandwidth.toFixed(2)),
          loss: parseFloat(avgLoss.toFixed(3)),
          slices: sliceCount,
        });
        return updated;
      });

      setLastUpdateTime(timestamp);
      setError(null);
      setIsLoading(false);
    } catch (err) {
      setError(err.message);
      console.error("Telemetry fetch error:", err);
    }
  };

  // Setup polling
  useEffect(() => {
    // Fetch immediately
    fetchTelemetry();

    // Setup auto-refresh interval
    let interval = null;
    if (autoRefresh) {
      interval = setInterval(fetchTelemetry, 5000); // 5 seconds
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh]);

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="custom-tooltip">
          <p className="label">{payload[0].payload.time}</p>
          {payload.map((entry, index) => (
            <p key={index} style={{ color: entry.color }}>
              {entry.name}:{" "}
              {typeof entry.value === "number"
                ? entry.value.toFixed(2)
                : entry.value}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="network-graph-container">
      <div className="graph-header">
        <h2>Network Metrics Dashboard</h2>
        <div className="graph-controls">
          <button
            className={`refresh-btn ${autoRefresh ? "active" : ""}`}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? "⏸ Pause" : "▶ Resume"} Auto-refresh
          </button>
          <button className="refresh-btn" onClick={fetchTelemetry}>
            🔄 Refresh Now
          </button>
          {lastUpdateTime && (
            <span className="last-update">
              Last update: {lastUpdateTime.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {error && <div className="error-banner">⚠️ Error: {error}</div>}

      {isLoading && latencyData.length === 0 ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading telemetry data...</p>
        </div>
      ) : (
        <div className="graphs-grid">
          {/* Latency Chart */}
          <div className="chart-card">
            <h3>Network Latency (ms)</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={latencyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 12 }}
                  interval={Math.max(0, Math.floor(latencyData.length / 6))}
                />
                <YAxis
                  label={{
                    value: "Latency (ms)",
                    angle: -90,
                    position: "insideLeft",
                  }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="latency"
                  stroke="#ef4444"
                  dot={false}
                  strokeWidth={2}
                  name="Average Latency"
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Bandwidth Utilization Chart */}
          <div className="chart-card">
            <h3>Total Bandwidth Utilization (Mbps)</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={bandwidthData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 12 }}
                  interval={Math.max(0, Math.floor(bandwidthData.length / 6))}
                />
                <YAxis
                  label={{
                    value: "Bandwidth (Mbps)",
                    angle: -90,
                    position: "insideLeft",
                  }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="bandwidth"
                  stroke="#3b82f6"
                  dot={false}
                  strokeWidth={2}
                  name="Total Bandwidth"
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Packet Loss Chart */}
          <div className="chart-card">
            <h3>Packet Loss Rate (%)</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={latencyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 12 }}
                  interval={Math.max(0, Math.floor(latencyData.length / 6))}
                />
                <YAxis
                  label={{
                    value: "Loss (%)",
                    angle: -90,
                    position: "insideLeft",
                  }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="loss"
                  stroke="#f97316"
                  dot={false}
                  strokeWidth={2}
                  name="Packet Loss %"
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Active Slices Count */}
          <div className="chart-card">
            <h3>Active Network Slices</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={sliceData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 12 }}
                  interval={Math.max(0, Math.floor(sliceData.length / 6))}
                />
                <YAxis
                  label={{ value: "Count", angle: -90, position: "insideLeft" }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Bar
                  dataKey="slices"
                  fill="#8b5cf6"
                  name="Active Slices"
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Combined Metrics View */}
          <div className="chart-card full-width">
            <h3>Combined Network Metrics</h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={allMetricsData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 12 }}
                  interval={Math.max(0, Math.floor(allMetricsData.length / 6))}
                />
                <YAxis
                  yAxisId="left"
                  label={{
                    value: "Latency (ms) / Bandwidth (Mbps)",
                    angle: -90,
                    position: "insideLeft",
                  }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  label={{
                    value: "Loss (%) / Slices",
                    angle: 90,
                    position: "insideRight",
                  }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="latency"
                  stroke="#ef4444"
                  dot={false}
                  strokeWidth={2}
                  name="Latency (ms)"
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="bandwidth"
                  stroke="#3b82f6"
                  dot={false}
                  strokeWidth={2}
                  name="Bandwidth (Mbps)"
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="loss"
                  stroke="#f97316"
                  dot={false}
                  strokeWidth={2}
                  name="Loss %"
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="slices"
                  stroke="#8b5cf6"
                  dot={false}
                  strokeWidth={2}
                  name="Active Slices"
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Legend and Info */}
      <div className="metrics-info">
        <h4>Metrics Description:</h4>
        <ul>
          <li>
            <span className="color-dot red"></span> <strong>Latency:</strong>{" "}
            Network delay in milliseconds
          </li>
          <li>
            <span className="color-dot blue"></span> <strong>Bandwidth:</strong>{" "}
            Total data transmission rate in Mbps
          </li>
          <li>
            <span className="color-dot orange"></span>{" "}
            <strong>Packet Loss:</strong> Percentage of lost packets
          </li>
          <li>
            <span className="color-dot purple"></span>{" "}
            <strong>Active Slices:</strong> Number of active network slices
          </li>
        </ul>
      </div>
    </div>
  );
}

export default NetworkGraph;
