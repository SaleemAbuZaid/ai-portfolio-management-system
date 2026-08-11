/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Decision Audit Log panel for persisted AI recommendations and execution-related evidence.
 */

import React from 'react';

const formatLatency = (value) => {
  const ms = Number(value);
  if (!Number.isFinite(ms) || ms <= 0 || ms >= 600000) return null;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
  return `${(ms / 60000).toFixed(1)} min`;
};

/**
 * Displays recommendation records as BUY, SELL, or HOLD audit entries.
 * The data is supplied by the root dashboard from AI recommendation/execution endpoints.
 */
const AdviceList = ({ recommendations }) => {
  const orderedRecommendations = Object.values(recommendations).sort((a, b) => {
    const aTime = Date.parse(a.timestamp || 0) || 0;
    const bTime = Date.parse(b.timestamp || 0) || 0;
    return bTime - aTime;
  });

  return (
    <div className="advice-list card glassmorphism h-100 shadow-sm border-0">
      <div className="card-header d-flex justify-content-between align-items-center">
        <h5 className="mb-0">Decision Audit Log</h5>
        <span className="x-small text-muted opacity-50 fw-bold">STEP 7 VERIFIED</span>
      </div>
      <div className="card-body overflow-auto p-0" style={{ maxHeight: '600px' }}>
        {Object.keys(recommendations).length === 0 ? (
          <div className="text-center text-muted py-5 px-4">
             <i className="bi bi-journal-text fs-2 opacity-25 mb-3 d-block"></i>
             <div className="small">Awaiting decision matrix persistence...</div>
          </div>
        ) : (
          <div className="list-group list-group-flush bg-transparent">
            {orderedRecommendations.map((rec, index) => {
               const isBuy = rec.action === 'BUY';
               const isHold = rec.action === 'HOLD';
               const colorClass = isBuy ? 'success' : (isHold ? 'info' : 'danger');
               const confidence = Math.min(1, Math.max(0, Number(rec.confidence ?? 0)));
               const latencyLabel = formatLatency(rec.latency_ms);
               
               return (
                <div key={index} className="list-group-item bg-transparent text-light border-secondary py-3 px-3 hover-brighten">
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <div className="d-flex align-items-center gap-2">
                       <span className="fw-bold text-white fs-6">{rec.ticker}</span>
                       <span className="x-small text-muted opacity-50">Signal</span>
                    </div>
                    <span className={`badge bg-${colorClass} border border-light`} style={{ minWidth: '60px' }}>
                      {rec.action}
                    </span>
                  </div>
                  
                  <div className="d-flex align-items-center gap-2 mb-2">
                    <div className="progress flex-grow-1" style={{ height: '5px', backgroundColor: 'rgba(255,255,255,0.1)' }}>
                      <div 
                        className={`progress-bar bg-${colorClass}`} 
                        style={{ width: `${(confidence * 100).toFixed(0)}%`, boxShadow: `0 0 8px var(--${colorClass})` }}
                      ></div>
                    </div>
                    <span className="x-small fw-bold text-white">{(confidence * 100).toFixed(0)}%</span>
                  </div>

                  <p className="small text-muted mb-2" style={{ fontSize: '11px', lineHeight: '1.3', fontStyle: 'italic' }}>
                    "{rec.reasoning}"
                  </p>
                  
                  <div className="d-flex justify-content-between align-items-center x-small opacity-75">
                    <span className="text-muted">
                       {new Date(rec.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <div className="d-flex align-items-center gap-2">
                       {latencyLabel ? (
                          <span className="text-info">{latencyLabel}</span>
                       ) : (
                          <span className="text-primary fw-bold">PERSISTED</span>
                       )}
                       <span className="text-muted opacity-50">Audit Provenance</span>
                    </div>
                  </div>
                </div>
               );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdviceList;
