/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Portfolio workspace for holdings, allocation charts, and source-aware rebalance advice.
 */

import React, { useMemo, useState } from 'react';
import axios from 'axios';
import { Pie } from 'react-chartjs-2';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';

ChartJS.register(ArcElement, Tooltip, Legend);

const API_BASE = process.env.REACT_APP_API_BASE || (
  (window.location.port === '3000' || window.location.port === '3001') 
    ? 'http://localhost:8000/api/v1' 
    : '/api/v1'
);

const formatMoney = (value) => {
    const numeric = Number(value || 0);
    return numeric.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
};

const formatPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;

const priceSourceClass = (source) => {
    const label = String(source || '').toUpperCase();
    if (label.includes('LIVE')) return 'border-success text-success';
    if (label.includes('DELAY') || label.includes('HISTORY')) return 'border-warning text-warning';
    return 'border-secondary text-muted';
};

/**
 * Shows the model portfolio, asset allocation, and AI Rebalance Intelligence.
 * Uses portfolio endpoints plus /portfolio/{id}/rebalance to display BUY/SELL/HOLD guidance.
 */
const PortfolioHub = ({ logSystem, portfolios, selectedId, setSelectedId, portfolio, fetchDetails, formatProviderLabel }) => {
    const [rebalanceData, setRebalanceData] = useState(null);
    const [rebalancing, setRebalancing] = useState(false);
    
    // Local form state for adding supported symbols to the selected model portfolio.
    const [newTicker, setNewTicker] = useState('AAPL');
    const [newQty, setNewQty] = useState(1);

    const SUPPORTED_TICKERS = [
        'AAPL', 'TSLA', 'BTC/USD', 'ETH/USD', 'XAU/USD', 'XAG/USD', 
        'EUR/USD', 'GBP/USD', 'USD/TRY', 'USD/JPY', 'WTI', 'BRENT'
    ];

    const handlePortfolioSelect = (event) => {
        setRebalanceData(null);
        setSelectedId(event.target.value);
    };

    const handleAddAsset = async () => {
        if (!selectedId || !newTicker) return;
        try {
            await axios.post(`${API_BASE}/portfolio/${selectedId}/assets`, {
                ticker: newTicker,
                quantity: parseFloat(newQty) || 1
            });
            logSystem(`Asset ${newTicker} added to portfolio ${selectedId}.`);
            setRebalanceData(null);
            fetchDetails(selectedId);
        } catch (err) {
            alert(`Failed to add asset: ${err.message}`);
        }
    };

    const handleDeleteAsset = async (ticker) => {
        if (!selectedId) return;
        const encodedTicker = encodeURIComponent(ticker);
        try {
            await axios.delete(`${API_BASE}/portfolio/${selectedId}/assets/${encodedTicker}`);
            logSystem(`Asset ${ticker} removed from portfolio ${selectedId}.`);
            setRebalanceData(null);
            fetchDetails(selectedId);
        } catch (err) {
            alert(`Failed to remove asset: ${err.message}`);
        }
    };

    const handleRebalance = async () => {
        // /portfolio/{id}/rebalance returns source-aware suggestions only; it
        // does not submit trades or change holdings automatically.
        if (!selectedId) return;
        setRebalancing(true);
        try {
            const res = await axios.post(`${API_BASE}/portfolio/${selectedId}/rebalance`);
            setRebalanceData(res.data);
            logSystem(`AI Rebalance complete for ${portfolio?.name}.`);
        } catch (err) {
            logSystem(`Rebalance Error: ${err.message}`);
        } finally {
            setRebalancing(false);
        }
    };

    const chartData = useMemo(() => ({
        labels: portfolio?.positions?.length 
            ? portfolio.positions.map(p => p.ticker) 
            : ['Cash'],
        datasets: [{
            data: portfolio?.positions?.length 
                ? portfolio.positions.map(p => p.market_value) 
                : [portfolio?.cash || 100],
            backgroundColor: [
                '#00d4ff', '#ff007a', '#36B37E', '#FF5630', 
                '#f39c12', '#9b59b6', '#34495e', '#16a085',
                '#27ae60', '#2980b9', '#8e44ad', '#2c3e50'
            ],
            borderWidth: 1,
            borderColor: 'rgba(255,255,255,0.1)'
        }]
    }), [portfolio]);

    return (
        <div className="portfolio-hub p-4">
            <div className="row g-4 mb-4">
                <div className="col-md-6">
                    <div className="card glassmorphism h-100 p-4">
                        <div className="d-flex justify-content-between align-items-center mb-4">
                            <h2 className="text-primary mb-0">Portfolio Selector</h2>
                            <select 
                                className="portfolio-selector" 
                                value={selectedId || ''} 
                                onChange={handlePortfolioSelect}
                            >
                                {portfolios.map(p => (
                                    <option key={p.id} value={p.id}>{p.name}</option>
                                ))}
                            </select>
                        </div>
                        
                        {portfolio && (
                            <div className="portfolio-summary mt-2">
                                <div className="row g-3">
                                    <div className="col-6">
                                        <div className="small text-muted text-uppercase">Risk Profile</div>
                                        <div className={`risk-badge risk-${portfolio.risk_profile.toLowerCase()} d-inline-block mt-1 ms-0`}>
                                            {portfolio.risk_profile}
                                        </div>
                                    </div>
                                    <div className="col-6 text-end">
                                        <div className="small text-muted text-uppercase">Status</div>
                                        <div className="badge bg-success mt-1">ACTIVE</div>
                                    </div>
                                    <div className="col-12 mt-4">
                                        <h1 className="display-4 fw-bold text-white mb-0">
                                            ${portfolio.total_value.toLocaleString()}
                                        </h1>
                                        <div className="text-muted">Model Portfolio Value</div>
                                    </div>
                                    <div className="col-6 mt-3">
                                        <h3 className="text-info mb-0">${portfolio.cash.toLocaleString()}</h3>
                                        <div className="small text-muted">Model Cash Balance</div>
                                    </div>
                                    <div className="col-6 mt-3 text-end">
                                        <div className="small text-muted">Last Updated</div>
                                        <div className="small text-white">
                                            {portfolio.updated_at ? new Date(portfolio.updated_at).toLocaleString() : 'Just now'}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                <div className="col-md-6">
                    <div className="card glassmorphism h-100 p-4">
                        <h4 className="text-white mb-4">Asset Allocation</h4>
                        <div className="allocation-chart-container">
                            <Pie 
                                data={chartData} 
                                options={{
                                    plugins: {
                                        legend: {
                                            position: 'right',
                                            labels: { color: '#a0aec0', font: { size: 12 } }
                                        }
                                    },
                                    maintainAspectRatio: false
                                }}
                            />
                        </div>
                    </div>
                </div>
            </div>

            <div className="row g-4 mb-4">
                <div className="col-lg-12">
                    <div className="card glassmorphism">
                        <div className="card-header d-flex justify-content-between align-items-center">
                            <h4 className="mb-0">Current Holdings</h4>
                            <div className="d-flex gap-2">
                                <select 
                                    className="portfolio-selector py-1"
                                    value={newTicker}
                                    onChange={(e) => setNewTicker(e.target.value)}
                                >
                                    {SUPPORTED_TICKERS.map(t => (
                                        <option key={t} value={t}>{t}</option>
                                    ))}
                                </select>
                                <input 
                                    type="number" 
                                    className="portfolio-selector py-1" 
                                    style={{ width: '80px' }}
                                    value={newQty}
                                    onChange={(e) => setNewQty(e.target.value)}
                                />
                                <button className="btn btn-primary btn-sm px-3" onClick={handleAddAsset}>Add Asset</button>
                            </div>
                        </div>
                        <div className="card-body p-0">
                            <div className="table-responsive">
                                <table className="table table-dark table-hover mb-0">
                                    <thead>
                                        <tr>
                                            <th className="ps-4">Ticker</th>
                                            <th>Quantity</th>
                                            <th>Avg Price</th>
                                            <th>Latest Price</th>
                                            <th>Market Value</th>
                                            <th>Weight</th>
                                            <th>Source</th>
                                            <th className="pe-4 text-end">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {portfolio?.positions?.map((p, idx) => (
                                            <tr key={idx}>
                                                <td className="ps-4 fw-bold text-primary">{p.ticker}</td>
                                                <td>{p.quantity.toFixed(4)}</td>
                                                <td className="text-muted">${p.avg_price.toFixed(2)}</td>
                                                <td className="fw-bold">${p.latest_price.toFixed(2)}</td>
                                                <td className="text-info">${p.market_value.toLocaleString()}</td>
                                                <td>{(p.weight * 100).toFixed(2)}%</td>
                                                <td>
                                                    <span className={`badge bg-dark border ${priceSourceClass(p.price_source)}`}>
                                                        {formatProviderLabel ? formatProviderLabel(p.price_source) : p.price_source}
                                                    </span>
                                                </td>
                                                <td className="pe-4 text-end">
                                                    <button 
                                                        className="btn btn-outline-danger btn-sm"
                                                        onClick={() => handleDeleteAsset(p.ticker)}
                                                    >
                                                        Delete
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                        {(!portfolio?.positions || portfolio.positions.length === 0) && (
                                            <tr>
                                                <td colSpan="8" className="text-center py-5 text-muted">
                                                    No assets in this portfolio. Add some to get started.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="row g-4">
                <div className="col-12">
                    <div className="card glassmorphism p-4 border-primary">
                        <div className="d-flex justify-content-between align-items-center mb-4">
                            <div>
                                <h3 className="text-primary mb-1">AI Rebalance Intelligence</h3>
                                <p className="text-muted small mb-0">
                                    Explainable risk-profile allocation using live portfolio weights, price-source quality, and drift thresholds.
                                </p>
                            </div>
                            <button 
                                className="rebalance-button" 
                                onClick={handleRebalance}
                                disabled={rebalancing}
                            >
                                {rebalancing ? 'Analyzing...' : 'Run AI Rebalance'}
                            </button>
                        </div>

                        {rebalanceData && (
                            <div className="rebalance-suggestions mt-4">
                                {rebalanceData.cash_position && (
                                    <div className="d-flex flex-wrap gap-3 align-items-center justify-content-between border border-secondary rounded p-3 mb-3 bg-dark">
                                        <div>
                                            <div className="x-small text-muted text-uppercase">Cash Discipline</div>
                                            <div className="small text-white">{rebalanceData.methodology}</div>
                                        </div>
                                        <div className="d-flex gap-4">
                                            <div>
                                                <div className="x-small text-muted">Current</div>
                                                <div className="small text-info">{formatPercent(rebalanceData.cash_position.current_weight)}</div>
                                            </div>
                                            <div>
                                                <div className="x-small text-muted">Target</div>
                                                <div className="small text-primary">{formatPercent(rebalanceData.cash_position.target_weight)}</div>
                                            </div>
                                            <div className="text-end">
                                                <div className="x-small text-muted">Model Portfolio Value</div>
                                                <div className="small text-white">{formatMoney(rebalanceData.portfolio_value)}</div>
                                            </div>
                                        </div>
                                    </div>
                                )}
                                <div className="row g-3">
                                    {rebalanceData.suggestions?.map((s, idx) => (
                                        <div className="col-md-4" key={idx}>
                                            <div className="card bg-dark border-secondary p-3 h-100">
                                                <div className="d-flex justify-content-between">
                                                    <span className="fw-bold text-white">{s.ticker}</span>
                                                    <span className={`badge-pill ${
                                                        s.action === 'BUY' ? 'bg-buy' : 
                                                        s.action === 'SELL' ? 'bg-sell' : 
                                                        s.action === 'HOLD' ? 'bg-hold' : 'bg-watch'
                                                    }`}>
                                                        {s.action}
                                                    </span>
                                                </div>
                                                <div className="mt-2">
                                                    <span className={`badge bg-dark border ${priceSourceClass(s.price_source)}`}>
                                                        {formatProviderLabel ? formatProviderLabel(s.price_source) : s.price_source}
                                                    </span>
                                                </div>
                                                <div className="row mt-3">
                                                    <div className="col-6">
                                                        <div className="x-small text-muted">Current Weight</div>
                                                        <div className="small">{formatPercent(s.current_weight)}</div>
                                                    </div>
                                                    <div className="col-6 text-end">
                                                        <div className="x-small text-muted">Target Weight</div>
                                                        <div className="small text-primary">{formatPercent(s.target_weight)}</div>
                                                    </div>
                                                </div>
                                                <div className="row mt-2">
                                                    <div className="col-6">
                                                        <div className="x-small text-muted">Drift</div>
                                                        <div className={Number(s.drift || 0) >= 0 ? 'small text-success' : 'small text-danger'}>
                                                            {formatPercent(s.drift)}
                                                        </div>
                                                    </div>
                                                    <div className="col-6 text-end">
                                                        <div className="x-small text-muted">Trade Value</div>
                                                        <div className={Number(s.trade_value || 0) >= 0 ? 'small text-success' : 'small text-danger'}>
                                                            {formatMoney(s.trade_value)}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="mt-2">
                                                    <div className="x-small text-muted">Reasoning</div>
                                                    <div className="small text-white" style={{ fontSize: '12px' }}>{s.reasoning}</div>
                                                </div>
                                                <div className="mt-auto pt-2 text-end">
                                                    <span className="x-small text-muted">Confidence: </span>
                                                    <span className="x-small text-info">{(s.confidence * 100).toFixed(0)}%</span>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default PortfolioHub;
