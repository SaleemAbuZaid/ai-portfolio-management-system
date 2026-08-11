/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Market Performance Audit chart for historical price movement and source freshness.
 */

import React, { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

/**
 * Renders selected asset history from /market/history and latest source metadata.
 * The chart title and badges reflect live, delayed, or fallback status from the backend.
 */
const PriceChart = ({ symbol, priceHistory, assetData, formatProviderLabel }) => {
  const data = useMemo(() => {
    const history = priceHistory[symbol] || [];
    return {
      labels: history.map(h => new Date(h.timestamp).toLocaleTimeString()),
      datasets: [
        {
          label: `${symbol} Price`,
          data: history.map(h => h.price),
          fill: true,
          borderColor: '#00d4ff',
          backgroundColor: 'rgba(0, 212, 255, 0.1)',
          tension: 0.4,
          pointRadius: 0,
        },
      ],
    };
  }, [symbol, priceHistory]);

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: 'index',
        intersect: false,
      },
    },
    scales: {
      x: {
        display: true,
        grid: { display: false },
        ticks: { color: '#8898aa', maxRotation: 0, autoSkip: true, maxTicksLimit: 5 }
      },
      y: {
        display: true,
        grid: { color: 'rgba(255, 255, 255, 0.05)' },
        ticks: { color: '#8898aa' }
      },
    },
    animation: false,
    transitions: {
      active: {
        animation: {
          duration: 0
        }
      }
    }
  };

  const getSourceBadge = () => {
    // Badge text comes directly from backend provenance labels so delayed and
    // fallback quotes are not visually promoted to live data.
    if (!assetData) return null;
    
    const sourceType = assetData.source_type || (assetData.is_live_provider ? 'LIVE_PROVIDER' : 'DELAYED_PROVIDER');
    
    if (sourceType === 'LIVE_PROVIDER') {
      return (
        <div className="d-flex align-items-center">
          <span className="status-dot me-2 pulse-slow" style={{ background: '#36B37E', boxShadow: '0 0 10px #36B37E' }}></span>
          <span className="badge bg-success text-white border border-light">LIVE FEED</span>
          {assetData.provider && (
             <span className="badge bg-dark text-muted ms-1 border border-secondary">{formatProviderLabel(assetData.provider)}</span>
          )}
        </div>
      );
    } else if (sourceType === 'INTERNAL_FALLBACK') {
      return (
        <div className="d-flex align-items-center">
          <span className="badge bg-primary text-white border border-light">FALLBACK</span>
          {assetData.provider && (
             <span className="badge bg-dark text-muted ms-1 border border-secondary">{formatProviderLabel(assetData.provider)}</span>
          )}
        </div>
      );
    } else {
      return (
        <div className="d-flex align-items-center">
          <span className="badge bg-warning text-dark border border-light">DELAYED</span>
          {assetData.provider && (
             <span className="badge bg-dark text-muted ms-1 border border-secondary">{formatProviderLabel(assetData.provider)}</span>
          )}
        </div>
      );
    }
  };

  return (
    <div className="price-chart card glassmorphism" style={{ minHeight: '380px' }}>
      <div className="card-header d-flex justify-content-between align-items-center py-3">
        <h5 className="mb-0 fw-bold">
          <span className="text-info me-2">{symbol}</span> 
          <span className="text-muted small">
            {assetData?.status === 'LIVE' ? 'Real-Time Performance' : 
             assetData?.status === 'FALLBACK' ? 'Fallback Continuity' : 
             'Market Performance Audit'}
          </span>
        </h5>
        {symbol && getSourceBadge()}
      </div>
      <div className="card-body p-3">
        <div style={{ height: '220px' }}>
          {symbol ? (
            <Line data={data} options={options} />
          ) : (
            <div className="h-100 d-flex align-items-center justify-content-center text-muted">
              Select an asset to view price history
            </div>
          )}
        </div>
        
        {assetData && (
          <div className="mt-3 px-2 py-1 border-top border-secondary opacity-75 d-flex justify-content-between align-items-center x-small">
            <span className="text-muted">
              Source: <span className="text-info">{formatProviderLabel(assetData.provider)}</span> ({assetData.source_type})
            </span>
            <span className="text-muted">
              Freshness: <span className={assetData.freshness_seconds < 60 ? 'text-success' : 'text-warning'}>
                {assetData.freshness_seconds}s ago
              </span>
              <span className="ms-2">Lag: {assetData.lag_ms?.toFixed(0)}ms</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default PriceChart;
