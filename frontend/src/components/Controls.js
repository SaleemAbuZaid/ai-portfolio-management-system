/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Reusable control component for dashboard interaction experiments.
 */
import React, { useState } from 'react';

const Controls = ({ onAdd, onRemove, onReset, portfolioId }) => {
  const [ticker, setTicker] = useState('');

  const handleAdd = () => {
    if (ticker) {
      onAdd(ticker.toUpperCase());
      setTicker('');
    }
  };

  const handleRemove = () => {
    if (ticker) {
      onRemove(ticker.toUpperCase());
      setTicker('');
    }
  };

  return (
    <div className="controls card glassmorphism">
      <div className="card-header">
        <h5>System Management</h5>
      </div>
      <div className="card-body">
        <div className="mb-4">
          <label className="form-label text-primary small text-uppercase fw-bold">Manual Asset Synchronization</label>
          <div className="input-group">
            <input 
              type="text" 
              className="form-control bg-dark text-light border-secondary" 
              placeholder="e.g. AAPL, BTCUSDT"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
            />
            <button className="btn btn-outline-primary" onClick={handleAdd}>Add</button>
            <button className="btn btn-outline-danger" onClick={handleRemove}>Remove</button>
          </div>
        </div>

        <div className="d-grid gap-2">
          <button 
            className="btn btn-primary py-2 fw-bold text-uppercase" 
            onClick={onReset}
            style={{ letterSpacing: '1px' }}
          >
            🚀 Run System Simulation
          </button>
          <small className="text-center text-muted" style={{ fontSize: '10px' }}>
            ID: {portfolioId} | TARGET: 100% COMPLIANCE
          </small>
        </div>
      </div>
    </div>
  );
};

export default Controls;
