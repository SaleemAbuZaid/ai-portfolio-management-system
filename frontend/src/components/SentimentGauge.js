/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - AI Sentiment Analysis gauge summarizing recent news polarity and distribution.
 */

import React from 'react';
import { Doughnut } from 'react-chartjs-2';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';

ChartJS.register(ArcElement, Tooltip, Legend);

/**
 * Displays aggregate sentiment score and distribution from the dashboard news state.
 * The source label tells reviewers which provider/provenance produced the sentiment sample.
 */
const SentimentGauge = ({ score, provider, stats, embedded = false }) => {
  // Normalize score (-1 to 1) to (0 to 180 degrees)
  const normalizedValue = ((score + 1) / 2) * 100;
  
  const data = {
    datasets: [{
      data: [normalizedValue, 100 - normalizedValue],
      backgroundColor: [
        score > 0 ? '#36B37E' : score < 0 ? '#FF5630' : '#FFAB00',
        'rgba(255, 255, 255, 0.05)'
      ],
      borderWidth: 0,
      circumference: 180,
      rotation: 270,
      cutout: '80%'
    }]
  };

  const options = {
    plugins: {
      legend: { display: false },
      tooltip: { enabled: false }
    },
    maintainAspectRatio: false,
    animation: false,
    transitions: {
      active: {
        animation: {
          duration: 0
        }
      }
    }
  };

  return (
    <div className={embedded ? 'sentiment-gauge sentiment-gauge-embedded' : 'sentiment-gauge card glassmorphism'}>
      <div className="card-header text-center py-2">
        <h6 className="mb-0 text-white fw-bold x-small ls-1">AI SENTIMENT ANALYSIS</h6>
      </div>
      <div className="card-body p-3">
        {score === null ? (
          <div className="text-center text-muted py-4">
             <div className="mb-2">No recent scored news</div>
             <div className="x-small">Feed waiting for live analysis...</div>
          </div>
        ) : (
          <div className="row align-items-center">
            <div className="col-6">
              <div style={{ height: '100px', width: '100%', position: 'relative' }}>
                <Doughnut data={data} options={options} />
                <div style={{
                  position: 'absolute',
                  bottom: '5%',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  textAlign: 'center'
                }}>
                  <h4 className="mb-0 fw-bold">{(score || 0).toFixed(2)}</h4>
                  <div className="x-small text-muted text-uppercase fw-bold" style={{ fontSize: '8px' }}>
                    {score > 0.15 ? 'Bullish' : score < -0.15 ? 'Bearish' : 'Neutral'}
                  </div>
                </div>
              </div>
              <div className="text-center x-small text-muted opacity-50 mt-2" style={{ fontSize: '8px' }}>
                SOURCE: {provider}
              </div>
            </div>
            <div className="col-6 border-start border-secondary border-opacity-10">
               <div className="x-small text-muted text-uppercase ls-1 mb-2">Distribution</div>
               <div className="d-flex flex-column gap-2">
                  <div className="d-flex justify-content-between align-items-center">
                    <span className="x-small text-success">POS</span>
                    <span className="fw-bold x-small">{stats?.distribution?.pos || 0}</span>
                  </div>
                  <div className="d-flex justify-content-between align-items-center">
                    <span className="x-small text-warning">NEU</span>
                    <span className="fw-bold x-small">{stats?.distribution?.neu || 0}</span>
                  </div>
                  <div className="d-flex justify-content-between align-items-center">
                    <span className="x-small text-danger">NEG</span>
                    <span className="fw-bold x-small">{stats?.distribution?.neg || 0}</span>
                  </div>
               </div>
               <div className="mt-2 pt-2 border-top border-secondary border-opacity-10">
                  <div className="x-small text-muted text-uppercase ls-1">Model Score</div>
                  <div className="small fw-bold text-info">TRUTH-ALIGNED</div>
               </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};


export default SentimentGauge;
