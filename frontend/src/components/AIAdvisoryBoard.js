/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Strategic AI intelligence matrix for price source, sentiment, prediction, advice,
 *   conviction, tactical reasoning, and latency audit display.
 */

import React from 'react';

/**
 * Renders the cross-asset AI decision matrix from /ai/advice/overview data.
 * Reviewers see provenance, model advice, confidence, and latency in one audit table.
 */
const AIAdvisoryBoard = ({ data, formatProviderLabel }) => {
  if (!data || data.length === 0) {
    return (
      <div className="card glassmorphism p-5 text-center text-muted">
        <div className="spinner-border text-primary mb-3" role="status"></div>
        <div className="fw-bold">Aggregating Market Intelligence...</div>
        <div className="x-small opacity-50 mt-1">Cross-referencing truth-aligned telemetry sources</div>
      </div>
    );
  }

  return (
    <div className="ai-advisory-board card glassmorphism mb-4 border-0 animate-fade-in shadow-lg">
      <div className="card-header bg-transparent border-bottom border-secondary py-3 d-flex justify-content-between align-items-center">
        <div className="d-flex align-items-center">
           <i className="bi bi-cpu text-info me-2 fs-5"></i>
           <h5 className="mb-0 fw-bold text-gradient">Strategic AI Intelligence Board</h5>
        </div>
        <div className="d-flex align-items-center gap-2">
            <span className="badge bg-primary text-white border border-info pulse-slow">TRUTH-ALIGNED</span>
            <span className="x-small text-muted opacity-50">DEFENSE READY</span>
        </div>
      </div>
      <div className="card-body p-0">
        <div className="table-responsive">
          <table className="table table-dark table-hover mb-0 align-middle">
            <thead className="sticky-top bg-dark" style={{ zIndex: 10, top: 0 }}>
              <tr className="text-muted small text-uppercase border-bottom border-secondary">
                <th className="ps-4 py-3" style={{ width: '120px' }}>Asset Matrix</th>
                <th className="py-3" style={{ width: '180px' }}>Price / Source</th>
                <th className="py-3" style={{ width: '110px' }}>Daily Sentiment</th>
                <th className="py-3" style={{ width: '130px' }}>Core Prediction</th>
                <th className="py-3" style={{ width: '100px' }}>System Advice</th>
                <th className="py-3" style={{ width: '100px' }}>Conviction</th>
                <th className="py-3" style={{ width: '25%' }}>Tactical Reasoning</th>
                <th className="pe-4 text-end py-3">Latency Audit</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, idx) => {
                 const sourceBadge = getSourceBadge(row);
                 const isLive = sourceBadge.label === 'LIVE';
                 const sentimentScore = Number(row.sentiment_score ?? 0);
                 const sentimentWidth = clampPercent(Math.abs(sentimentScore) * 100);
                 const confidence = Math.min(1, Math.max(0, Number(row.confidence ?? 0)));
                 
                 const latencyStr = formatLatency(row.price_lag_ms);
                 const isHighLatency = Number(row.price_lag_ms) >= 1000;

                 return (
                  <tr key={idx} className={isLive ? 'border-start border-4 border-success' : ''}>
                    <td className="ps-4 py-3">
                      <div className="fw-bold text-white fs-6">{row.ticker}</div>
                      <div className="x-small text-muted opacity-50">{row.asset_class}</div>
                    </td>
                    <td className="py-3">
                      <div className="fw-bold text-info">
                          {row.latest_price ? row.latest_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: (row.ticker.includes('/') ? 4 : 2) }) : 'N/A'}
                      </div>
                      <div className="d-flex align-items-center gap-1 x-small opacity-75">
                         <span className={`badge bg-${sourceBadge.color} x-small`} style={{ fontSize: '0.6rem' }}>{sourceBadge.label}</span>
                         <span className="text-muted">{formatProviderLabel ? formatProviderLabel(row.price_provider) : row.price_provider}</span>
                      </div>
                    </td>
                    <td className="py-3">
                      <div className="d-flex flex-column" style={{ minWidth: '90px' }}>
                          <span className={`text-${getSentimentColor(row.sentiment_label)} fw-bold x-small text-uppercase mb-1`}>
                            {row.sentiment_label}
                          </span>
                          <div className="progress bg-dark" style={{ height: '3px' }}>
                            <div 
                                className={`progress-bar bg-${getSentimentColor(row.sentiment_label)}`} 
                                style={{ width: `${sentimentWidth}%` }}
                            ></div>
                          </div>
                      </div>
                    </td>
                    <td className="py-3">
                      <div className="fw-bold text-light opacity-90">{row.prediction_label}</div>
                      <div className="x-small text-muted opacity-50">Trend Basis</div>
                    </td>
                    <td className="py-3">
                      <span className={`badge bg-${getAdviceColor(row.recommendation)} border border-light w-100 py-2`}>
                        {row.recommendation}
                      </span>
                    </td>
                    <td className="py-3">
                      {confidence <= 0.01 ? (
                        <span className="badge bg-secondary opacity-50 border border-secondary text-muted">LOW</span>
                      ) : (
                        <div className="d-flex flex-column" style={{ minWidth: '80px' }}>
                          <div className="d-flex justify-content-between x-small mb-1">
                            <span className="text-muted">{(confidence * 100).toFixed(1)}%</span>
                            <span className="text-info opacity-75">Conviction</span>
                          </div>
                          <div className="progress bg-dark" style={{ height: '4px' }}>
                            <div 
                              className={`progress-bar bg-info`} 
                              style={{ width: `${clampPercent(confidence * 100)}%`, boxShadow: '0 0 5px var(--info)' }}
                            ></div>
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="py-3">
                      <div className="text-wrap text-muted small-reasoning" style={{ fontSize: '0.75rem', lineHeight: '1.4', maxWidth: '300px' }}>
                        {row.reasoning}
                      </div>
                    </td>
                    <td className="text-end py-3 pe-4">
                      <span className={latencyStr === 'N/A' ? 'text-muted opacity-50' : (isHighLatency ? 'text-warning' : 'text-success')}>
                        {latencyStr}
                      </span>
                    </td>
                  </tr>
                 );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

const clampPercent = (value) => Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0)).toFixed(0);

const formatLatency = (value) => {
  const ms = Number(value);
  if (!Number.isFinite(ms) || ms <= 0 || ms > 31536000000) return 'N/A';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
  return `${(ms / 60000).toFixed(1)} min`;
};

const getSourceBadge = (row) => {
  // Collapse backend source_type/provider metadata into the compact badges used
  // by the AI table while preserving fallback/history distinctions.
  const source = String(row.source_type || row.price_provider || '').toUpperCase();
  const provider = String(row.price_provider || '').toUpperCase();
  if (source.includes('FALLBACK') || provider.includes('FALLBACK') || source.includes('MISSING') || provider === 'ERROR') {
    return { label: 'FALLBACK', color: 'secondary' };
  }
  if (source.includes('LIVE')) {
    return { label: 'LIVE', color: 'success' };
  }
  if (source.includes('HISTORY')) {
    return { label: 'HISTORY', color: 'secondary' };
  }
  return { label: 'DELAYED', color: 'warning' };
};

const getSentimentColor = (label) => {
  const l = String(label).toUpperCase();
  if (l.includes('BULLISH') || l.includes('POSITIVE')) return 'success';
  if (l.includes('BEARISH') || l.includes('NEGATIVE')) return 'danger';
  return 'warning';
};

const getAdviceColor = (advice) => {
  switch (advice) {
    case 'BUY': return 'success';
    case 'SELL': return 'danger';
    case 'HOLD': return 'primary';
    case 'WAIT': return 'warning';
    case 'WATCH': return 'info';
    case 'INSUFFICIENT_DATA': return 'secondary text-muted';
    default: return 'secondary';
  }
};

export default AIAdvisoryBoard;
