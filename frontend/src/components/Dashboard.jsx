import React, { useState, useEffect } from "react";
import "../styles/Dashboard.css";

/**
 * Dashboard Component
 *
 * Main overview dashboard displaying:
 * - Current active slices
 * - Quick slice management
 * - Network health summary
 * - Recent orchestrator actions
 */
function Dashboard() {
  const [slices, setSlices] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newSlice, setNewSlice] = useState({
    slice_name: "",
    slice_type: "iot",
    priority: 70,
    bandwidth_mbps: 50,
    delay_ms: 100,
    loss_percent: 1,
    duration_minutes: 60,
  });

  /**
   * Fetch all slices from backend
   */
  const fetchSlices = async () => {
    try {
      const response = await fetch("http://localhost:8000/api/slices/");
      if (!response.ok) throw new Error("Failed to fetch slices");
      const data = await response.json();
      setSlices(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error("Fetch error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSlices();
    // Refresh every 10 seconds
    const interval = setInterval(fetchSlices, 10000);
    return () => clearInterval(interval);
  }, []);

  /**
   * Create a new slice
   */
  const handleCreateSlice = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(
        "http://localhost:8000/api/slices/create_slice",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(newSlice),
        },
      );
      if (response.ok) {
        setShowCreateModal(false);
        setNewSlice({
          slice_name: "",
          slice_type: "iot",
          priority: 70,
          bandwidth_mbps: 50,
          delay_ms: 100,
          loss_percent: 1,
          duration_minutes: 60,
        });
        fetchSlices();
      } else {
        throw new Error("Failed to create slice");
      }
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  };

  /**
   * Delete a slice
   */
  const handleDeleteSlice = async (sliceId) => {
    if (!confirm("Are you sure you want to terminate this slice?")) return;
    try {
      const response = await fetch(
        `http://localhost:8000/api/slices/${sliceId}`,
        {
          method: "DELETE",
        },
      );
      if (response.ok) {
        fetchSlices();
      } else {
        throw new Error("Failed to delete slice");
      }
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  };

  /**
   * Get color for QoE score
   */
  const getQoEColor = (status) => {
    switch (status) {
      case "excellent":
        return "#10b981";
      case "good":
        return "#3b82f6";
      case "fair":
        return "#f59e0b";
      case "poor":
        return "#ef4444";
      default:
        return "#6b7280";
    }
  };

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h2>Dashboard Overview</h2>
        <button
          className="create-slice-btn"
          onClick={() => setShowCreateModal(true)}
        >
          ➕ Create New Slice
        </button>
      </div>

      {error && <div className="error-banner">⚠️ Error: {error}</div>}

      {isLoading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading slices...</p>
        </div>
      ) : (
        <>
          {/* Stats Cards */}
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{slices.length}</div>
              <div className="stat-label">Active Slices</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">
                {slices
                  .reduce((sum, s) => sum + (s.bandwidth_mbps || 0), 0)
                  .toFixed(0)}
              </div>
              <div className="stat-label">Total Bandwidth (Mbps)</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">
                {slices.filter((s) => s.status === "active").length}
              </div>
              <div className="stat-label">Healthy Slices</div>
            </div>
          </div>

          {/* Slices Table */}
          <div className="slices-section">
            <h3>Active Network Slices</h3>
            {slices.length === 0 ? (
              <div className="empty-state">
                <p>No active slices. Create one to get started.</p>
              </div>
            ) : (
              <div className="slices-table-wrapper">
                <table className="slices-table">
                  <thead>
                    <tr>
                      <th>Slice Name</th>
                      <th>Type</th>
                      <th>Priority</th>
                      <th>Bandwidth</th>
                      <th>Delay SLA</th>
                      <th>Status</th>
                      <th>Created</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {slices.map((slice) => (
                      <tr key={slice.slice_id}>
                        <td className="name-cell">
                          <span className="slice-name">{slice.slice_name}</span>
                        </td>
                        <td>
                          <span className="badge">
                            {slice.slice_type.toUpperCase()}
                          </span>
                        </td>
                        <td>{slice.priority}</td>
                        <td>{slice.bandwidth_mbps} Mbps</td>
                        <td>{slice.delay_ms}ms</td>
                        <td>
                          <span
                            className="status-badge"
                            style={{
                              backgroundColor: getQoEColor(slice.status),
                            }}
                          >
                            {slice.status.toUpperCase()}
                          </span>
                        </td>
                        <td className="time-cell">
                          {new Date(slice.created_at).toLocaleString()}
                        </td>
                        <td className="actions-cell">
                          <button
                            className="action-btn delete-btn"
                            onClick={() => handleDeleteSlice(slice.slice_id)}
                            title="Delete slice"
                          >
                            🗑️
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* Create Slice Modal */}
      {showCreateModal && (
        <div
          className="modal-overlay"
          onClick={() => setShowCreateModal(false)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Create New Network Slice</h3>
              <button
                className="close-btn"
                onClick={() => setShowCreateModal(false)}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateSlice} className="create-form">
              <div className="form-group">
                <label>Slice Name:</label>
                <input
                  type="text"
                  value={newSlice.slice_name}
                  onChange={(e) =>
                    setNewSlice({ ...newSlice, slice_name: e.target.value })
                  }
                  placeholder="e.g., Gaming Session 1"
                  required
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Type:</label>
                  <select
                    value={newSlice.slice_type}
                    onChange={(e) =>
                      setNewSlice({ ...newSlice, slice_type: e.target.value })
                    }
                  >
                    <option value="video">Video</option>
                    <option value="gaming">Gaming</option>
                    <option value="iot">IoT</option>
                    <option value="voip">VoIP</option>
                    <option value="custom">Custom</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Priority (1-100):</label>
                  <input
                    type="number"
                    min="1"
                    max="100"
                    value={newSlice.priority}
                    onChange={(e) =>
                      setNewSlice({
                        ...newSlice,
                        priority: parseInt(e.target.value),
                      })
                    }
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Bandwidth (Mbps):</label>
                  <input
                    type="number"
                    min="0.1"
                    step="0.1"
                    value={newSlice.bandwidth_mbps}
                    onChange={(e) =>
                      setNewSlice({
                        ...newSlice,
                        bandwidth_mbps: parseFloat(e.target.value),
                      })
                    }
                  />
                </div>

                <div className="form-group">
                  <label>Max Delay (ms):</label>
                  <input
                    type="number"
                    min="0"
                    value={newSlice.delay_ms}
                    onChange={(e) =>
                      setNewSlice({
                        ...newSlice,
                        delay_ms: parseFloat(e.target.value),
                      })
                    }
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Max Loss (%):</label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    step="0.1"
                    value={newSlice.loss_percent}
                    onChange={(e) =>
                      setNewSlice({
                        ...newSlice,
                        loss_percent: parseFloat(e.target.value),
                      })
                    }
                  />
                </div>

                <div className="form-group">
                  <label>Duration (minutes):</label>
                  <input
                    type="number"
                    min="1"
                    value={newSlice.duration_minutes}
                    onChange={(e) =>
                      setNewSlice({
                        ...newSlice,
                        duration_minutes: parseInt(e.target.value),
                      })
                    }
                  />
                </div>
              </div>

              <div className="form-actions">
                <button type="submit" className="submit-btn">
                  Create Slice
                </button>
                <button
                  type="button"
                  className="cancel-btn"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
