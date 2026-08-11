/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Portfolio allocation chart component for visualizing asset weights.
 */
import React from 'react';
import { Doughnut } from 'react-chartjs-2';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';

ChartJS.register(ArcElement, Tooltip, Legend);

const PortfolioPie = ({ data }) => {
  const chartData = {
    labels: data.labels,
    datasets: [{
      data: data.values,
      backgroundColor: [
        '#0052CC', '#36B37E', '#FFAB00', '#FF5630', '#6554C0', '#00B8D9', '#36B37E', '#FF8B00'
      ],
      borderWidth: 2,
      borderColor: '#1a1d21',
      hoverOffset: 10
    }]
  };

  const options = {
    plugins: {
      legend: {
        position: 'bottom',
        labels: { color: '#8898aa', padding: 20, usePointStyle: true }
      }
    },
    maintainAspectRatio: false,
    cutout: '70%',
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
    <div className="portfolio-pie card glassmorphism h-100">
      <div className="card-header">
        <h5>Asset Allocation</h5>
      </div>
      <div className="card-body p-4">
        <div style={{ height: '250px' }}>
          {data.labels.length > 0 ? (
            <Doughnut data={chartData} options={options} />
          ) : (
            <div className="h-100 d-flex align-items-center justify-content-center text-muted">
              Portfolio empty
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PortfolioPie;
