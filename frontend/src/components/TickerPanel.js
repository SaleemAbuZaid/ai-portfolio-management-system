/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Market Dynamics Feed showing the truth-aligned watchlist and embedded sentiment panel.
 */

import React from 'react';

/**
 * Displays current asset prices, daily trend, and provenance for the watchlist.
 * Data comes from the dashboard market snapshot and retains live/fallback status badges.
 */
const TickerPanel = ({ watchlist, onSelect, formatProviderLabel, sentimentPanel }) => {
  const list = Object.values(watchlist || {}).sort((a,b) => (a.symbol > b.symbol ? 1 : -1));

  return (
    <div className="ticker-panel card glassmorphism shadow-lg border-0">
      <div className="card-header bg-dark bg-opacity-25 border-bottom border-secondary border-opacity-10 py-3 d-flex justify-content-between align-items-center">
        <h5 className="mb-0 text-white d-flex align-items-center">
            <i className="bi bi-graph-up-arrow text-primary me-2 fs-5"></i>
            Market Dynamics Feed
        </h5>
        <span className="x-small text-muted text-uppercase fw-bold opacity-50 ls-1">Truth-Aligned Watchlist</span>
      </div>
      <div className="card-body p-0">
        <div className="ticker-intelligence-layout">
          {sentimentPanel && (
            <div className="ticker-sentiment-strip">
              {sentimentPanel}
            </div>
          )}
          <div className="ticker-watchlist-pane table-responsive">
          <table className="table table-dark table-hover mb-0 text-center align-middle border-0">
            <thead>
              <tr className="text-muted small text-uppercase font-monospace" style={{ fontSize: '0.75rem' }}>
                <th className="ps-4 text-start border-0">Asset</th>
                <th className="border-0">Price</th>
                <th className="border-0">Daily Trend</th>
                <th className="pe-4 text-end border-0">Provenance</th>
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <tr>
                  <td colSpan="4" className="text-center text-muted py-5">
                    <div className="spinner-border spinner-border-sm text-primary mb-2" role="status"></div>
                    <div className="small fw-bold">Synchronizing with market mesh...</div>
                  </td>
                </tr>
              ) : (
                list.map((tick) => {
                   const sym = tick.symbol || tick.ticker;
                   const isLive = tick.status === 'LIVE' || tick.source_type === 'LIVE_PROVIDER';
                   const isFallback = tick.status === 'FALLBACK' || tick.source_type === 'INTERNAL_FALLBACK';
                   
                   // Null trend means the backend lacked enough history to
                   // compute movement without overstating price direction.
                   const rawTrend = tick.change_pct ?? tick.change;
                   const hasTrend = rawTrend !== null && rawTrend !== undefined;
                   const trend = Number(rawTrend || 0);
                   
                   return (
                    <tr key={sym} onClick={() => onSelect && onSelect(sym)} style={{ cursor: 'pointer' }} className={`hover-brighten transition-all ${isLive ? 'border-start border-3 border-success' : ''}`}>
                      <td className="ps-4 text-start">
                        <div className="d-flex flex-column">
                          <span className="fw-bold text-white" style={{ letterSpacing: '0.05em' }}>{sym}</span>
                          <span className="x-small text-muted opacity-50 text-uppercase">{tick.asset_class || 'EQUITY'}</span>
                        </div>
                      </td>
                      <td className="fw-bold text-info font-monospace">
                        ${Number(tick.price || tick.latest_price || 0).toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: (sym.includes('/') ? 4 : 2)
                        })}
                      </td>
                      <td>
                        {!hasTrend ? (
                          <span className="badge bg-dark text-muted border border-secondary border-opacity-25 py-1 px-2" style={{ fontSize: '0.65rem' }} title="Insufficient 24h market history for trend calculation">
                            LOW DATA
                          </span>
                        ) : (
                          <span className={`badge border-0 ${trend >= 0 ? 'bg-success bg-opacity-25 text-success' : 'bg-danger bg-opacity-25 text-danger'} py-1 px-2`} style={{ minWidth: '70px', fontSize: '0.8rem' }}>
                            {trend >= 0 ? '+' : ''}{trend.toFixed(2)}%
                          </span>
                        )}
                      </td>
                      <td className="pe-4 text-end">
                        <div className="d-flex flex-column align-items-end">
                          <span className={`badge ${isLive ? 'bg-success' : isFallback ? 'bg-primary' : 'bg-warning'} text-uppercase py-1 px-2 mb-1`} style={{ fontSize: '0.6rem' }}>
                            {tick.source_type?.replace('_PROVIDER', '') || (isLive ? 'LIVE' : 'DELAYED')}
                          </span>
                          <span className="text-muted font-monospace opacity-50" style={{ fontSize: '0.6rem' }}>
                            {formatProviderLabel ? formatProviderLabel(tick.provider || tick.source) : 'INTERNAL'}
                          </span>
                        </div>
                      </td>
                    </tr>
                   );
                })
              )}
            </tbody>
          </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TickerPanel;
