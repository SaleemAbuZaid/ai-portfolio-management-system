/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Global Intelligence Stream for live/delayed/fallback news and sentiment provenance.
 */

import React from 'react';

function parseDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatRelativeTime(value) {
  const date = parseDate(value);
  if (!date) return 'updating';
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 15) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function formatClock(value) {
  const date = parseDate(value);
  if (!date) return '--:--';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Renders normalized news from /news/latest with provider and source_type labels.
 * Users see live provider articles first, with fallback rows clearly marked when present.
 */
const NewsFeed = ({ news, decodeEntities, formatProviderLabel, stats }) => {
  return (
    <div className="news-feed card glassmorphism shadow-lg border-0">
      <div className="card-header bg-dark bg-opacity-25 border-bottom border-secondary border-opacity-10 py-3 d-flex justify-content-between align-items-center">
        <h5 className="mb-0 text-white d-flex align-items-center">
            <i className="bi bi-broadcast text-info me-2 fs-5"></i>
            Global Intelligence Stream
        </h5>
        <div className="d-flex align-items-center gap-1">
            <span className="status-dot pulse-slow bg-info" style={{ width: '8px', height: '8px', borderRadius: '50%' }}></span>
            <span className="x-small text-muted opacity-50 fw-bold ls-1">LIVE INGEST</span>
        </div>
      </div>
      <div className="card-body overflow-auto p-0" style={{ maxHeight: '650px' }}>
        {news.length === 0 ? (
          <div className="text-center text-muted py-5 px-4">
            <div className="spinner-border spinner-border-sm text-info mb-3" role="status"></div>
            <div className="small fw-bold">Synchronizing with global news pipelines...</div>
            <div className="x-small opacity-50 mt-1 italic">EventRegistry & FinBERT connectivity active</div>
          </div>
        ) : (
          <div className="list-group list-group-flush bg-transparent">
            {news.map((item, index) => {
               // Items are already normalized by App.js; this component only
               // renders provider/source labels and sentiment state.
               const sentiment = item.sentiment?.label || item.sentiment_label || 'NEUTRAL';
               const score = item.sentiment?.score ?? item.sentiment_score ?? 0;
               const isPositive = score > 0.15;
               const isNegative = score < -0.15;
               const prov = formatProviderLabel ? formatProviderLabel(item.provider) : (item.provider || 'RSS');
               const syncTime = item.received_at || item.last_updated || (item.ingest_ts ? item.ingest_ts * 1000 : null);
               const publishedTime = item.published_at || item.timestamp;
               const displayClock = publishedTime || syncTime;
               const timeTitle = [
                 syncTime ? `Synced: ${formatClock(syncTime)}` : null,
                 publishedTime ? `Published: ${formatClock(publishedTime)}` : null
               ].filter(Boolean).join(' | ');
               
               return (
                <div key={index} className="list-group-item bg-transparent text-light border-secondary border-opacity-10 py-3 px-4 hover-brighten transition-all">
                  <div className="d-flex justify-content-between align-items-start mb-2">
                    <div className="d-flex align-items-center gap-2">
                      <span className="text-info x-small fw-bold ls-1">{prov}</span>
                      {item.source_type && (
                         <span className={`x-small px-2 py-0 rounded-pill ${item.source_type === 'LIVE_PROVIDER' ? 'bg-success bg-opacity-25 text-success border border-success border-opacity-25' : 'bg-dark text-muted border border-secondary border-opacity-25'}`} style={{ fontSize: '0.6rem' }}>
                           {item.source_type.replace('_PROVIDER', '')}
                         </span>
                      )}
                    </div>
                    <span className={`badge px-2 py-1 ${isPositive ? 'bg-success' : isNegative ? 'bg-danger' : 'bg-warning text-dark'} shadow-sm`} style={{ fontSize: '0.65rem' }}>
                      {sentiment} ({(score).toFixed(2)})
                    </span>
                  </div>
                  <div className="fw-bold text-white mb-2" style={{ lineHeight: '1.4', fontSize: '0.9rem', letterSpacing: '0.01em' }}>
                    {decodeEntities ? decodeEntities(item.headline || item.title) : (item.headline || item.title)}
                  </div>
                  <div className="d-flex justify-content-between align-items-center opacity-50 font-monospace" style={{ fontSize: '0.65rem' }}>
                    <span className="text-info opacity-75"><i className="bi bi-bank me-1"></i>{item.source || 'WIRE'}</span>
                    <span className="text-muted" title={timeTitle || undefined}>
                      <i className="bi bi-arrow-repeat me-1"></i>{formatRelativeTime(syncTime)}
                      <span className="mx-1">/</span>
                      <i className="bi bi-clock me-1"></i>{formatClock(displayClock)}
                    </span>
                  </div>
                </div>
               );
            })}
          </div>
        )}
      </div>
      <div className="card-footer bg-dark bg-opacity-25 border-top border-secondary border-opacity-10 p-3">
        <div className="row g-2 text-center">
          <div className="col-4">
            <div className="x-small text-muted text-uppercase ls-1">Provenance</div>
            <div className="small fw-bold text-info">{stats?.live_count || 0} LIVE</div>
          </div>
          <div className="col-4 border-start border-end border-secondary border-opacity-10">
            <div className="x-small text-muted text-uppercase ls-1">Sentiment</div>
            <div className="small fw-bold text-success">{( (stats?.pos || 0) / (stats?.total || 1) * 100).toFixed(0)}% POS</div>
          </div>
          <div className="col-4">
            <div className="x-small text-muted text-uppercase ls-1">Last Sync</div>
            <div className="small fw-bold text-muted">{stats?.last_sync ? formatRelativeTime(stats.last_sync) : '--:--'}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NewsFeed;
