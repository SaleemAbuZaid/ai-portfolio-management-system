/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Broker management panel for Alpaca Paper status, orders, positions, and execution proof context.
 */

import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_BASE || (
  (window.location.port === '3000' || window.location.port === '3001') 
    ? 'http://localhost:8000/api/v1' 
    : '/api/v1'
);

/**
 * Polls Alpaca Paper-facing broker endpoints and displays account, order, and position telemetry.
 * The panel supports defense review of live paper execution without exposing credentials.
 */
const BrokerPanel = () => {
    const [status, setStatus] = useState(null);
    const [orders, setOrders] = useState([]);
    const [positions, setPositions] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        // Broker endpoints return Alpaca Paper status, order history, and
        // positions; credentials stay server-side and are never rendered here.
        try {
            setLoading(true);
            const [statusRes, ordersRes, positionsRes] = await Promise.all([
                axios.get(`${API_BASE}/broker/status`),
                axios.get(`${API_BASE}/broker/orders`),
                axios.get(`${API_BASE}/broker/positions`)
            ]);
            setStatus(statusRes.data);
            setOrders(ordersRes.data || []);
            setPositions(positionsRes.data || []);
        } catch (err) {
            console.error("Broker fetch error", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, []);

    if (loading && !status) return (
        <div className="p-5 text-center text-muted">
            <div className="spinner-border text-info mb-3" role="status"></div>
            <div className="fw-bold">Synchronizing with Alpaca Paper API...</div>
            <div className="x-small opacity-50">Validating brokerage credentials and portfolio metadata</div>
        </div>
    );

    return (
        <div className="broker-panel p-4 animate-fade-in">
            <div className="row g-4 mb-4">
                <div className="col-12">
                    <div className="card glassmorphism p-4 border-0 shadow-lg" style={{ background: 'linear-gradient(135deg, rgba(13, 202, 240, 0.05), rgba(0, 0, 0, 0.4))' }}>
                        <div className="d-flex justify-content-between align-items-center">
                            <div>
                                <h3 className="text-white mb-1 d-flex align-items-center">
                                    <i className="bi bi-bank text-info me-3"></i>
                                    Alpaca Broker Management
                                </h3>
                                <p className="text-muted small mb-0 ls-1">Institutional-grade execution proofs & paper trading environment telemetry.</p>
                            </div>
                            <div className="text-end">
                                <span className={`badge ${status?.account_status === 'ACTIVE' ? 'bg-success' : 'bg-danger'} px-4 py-2 shadow-sm`} style={{ letterSpacing: '0.1em' }}>
                                    ACCOUNT: {status?.account_status || 'DISCONNECTED'}
                                </span>
                                <div className="x-small text-muted mt-2 font-monospace opacity-50">PID: {status?.account_number || 'UNKNOWN'} | {status?.provider}</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="row g-4 mb-4">
                <div className="col-md-3">
                    <div className="card glassmorphism p-4 text-center border-0 shadow-sm hover-brighten">
                        <div className="x-small text-muted text-uppercase mb-2 fw-bold ls-1">Liquid Cash</div>
                        <h2 className="text-white font-monospace mb-1">${status?.cash?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}</h2>
                        <div className="x-small text-success opacity-75">Base: {status?.currency}</div>
                    </div>
                </div>
                <div className="col-md-3">
                    <div className="card glassmorphism p-4 text-center border-0 shadow-sm hover-brighten">
                        <div className="x-small text-muted text-uppercase mb-2 fw-bold ls-1">AUM Value</div>
                        <h2 className="text-info font-monospace mb-1">${status?.portfolio_value?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}</h2>
                        <div className="x-small text-muted opacity-50 italic">Total Market Value</div>
                    </div>
                </div>
                <div className="col-md-3">
                    <div className="card glassmorphism p-4 text-center border-0 shadow-sm hover-brighten">
                        <div className="x-small text-muted text-uppercase mb-2 fw-bold ls-1">Buying Power</div>
                        <h2 className="text-warning font-monospace mb-1">${status?.buying_power?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}</h2>
                        <div className="x-small text-muted opacity-50">Standard Leverage: 4x</div>
                    </div>
                </div>
                <div className="col-md-3">
                    <div className="card glassmorphism p-4 text-center border-0 shadow-sm hover-brighten" style={{ borderLeft: '3px solid var(--info)' }}>
                        <div className="x-small text-muted text-uppercase mb-2 fw-bold ls-1">Maintenance Margin</div>
                        <h2 className="text-light font-monospace mb-1" style={{ fontSize: '1.5rem' }}>
                            ${(status?.maintenance_margin || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </h2>
                        <div className="x-small text-info opacity-75">Mode: Live Paper</div>
                    </div>
                </div>
            </div>

            <div className="row g-4">
                <div className="col-lg-7">
                    <div className="card glassmorphism border-0 shadow-lg">
                        <div className="card-header bg-dark bg-opacity-25 border-bottom border-secondary border-opacity-10 py-3">
                            <h5 className="mb-0 text-white d-flex align-items-center">
                                <i className="bi bi-clock-history text-info me-2"></i>
                                Recent Order History
                            </h5>
                        </div>
                        <div className="card-body p-0">
                            <div className="table-responsive" style={{ maxHeight: '450px' }}>
                                <table className="table table-dark table-hover mb-0 align-middle border-0">
                                    <thead>
                                        <tr className="text-muted x-small text-uppercase font-monospace">
                                            <th className="ps-4 border-0">Asset</th>
                                            <th className="border-0">Side</th>
                                            <th className="border-0">Qty</th>
                                            <th className="border-0">Status</th>
                                            <th className="border-0">Execution Price</th>
                                            <th className="pe-4 text-end border-0">Timestamp</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {orders.map((o, idx) => (
                                            <tr key={idx} className="border-bottom border-secondary border-opacity-10">
                                                <td className="ps-4 fw-bold text-white">{o.symbol}</td>
                                                <td>
                                                    <span className={`badge ${o.side === 'buy' ? 'bg-primary bg-opacity-25 text-primary border border-primary border-opacity-25' : 'bg-danger bg-opacity-25 text-danger border border-danger border-opacity-25'} px-2 py-1`} style={{ fontSize: '0.65rem' }}>
                                                        {o.side?.toUpperCase()}
                                                    </span>
                                                </td>
                                                <td className="font-monospace text-light">{o.qty}</td>
                                                <td>
                                                    <span className={`badge ${o.status === 'filled' ? 'bg-success' : 'bg-secondary'} rounded-pill px-2 py-1 shadow-sm`} style={{ fontSize: '0.6rem' }}>
                                                        {o.status?.toUpperCase()}
                                                    </span>
                                                </td>
                                                <td className="text-info font-monospace">{o.filled_avg_price ? `$${parseFloat(o.filled_avg_price).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '--'}</td>
                                                <td className="pe-4 text-end text-muted x-small font-monospace opacity-75">
                                                    {new Date(o.submitted_at).toLocaleTimeString()}
                                                </td>
                                            </tr>
                                        ))}
                                        {orders.length === 0 && (
                                            <tr><td colSpan="6" className="text-center py-5 text-muted italic">No recent execution logs found in Alpaca registry.</td></tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="col-lg-5">
                    <div className="card glassmorphism border-0 shadow-lg">
                        <div className="card-header bg-dark bg-opacity-25 border-bottom border-secondary border-opacity-10 py-3">
                            <h5 className="mb-0 text-white d-flex align-items-center">
                                <i className="bi bi-pie-chart text-primary me-2"></i>
                                Current Portfolio Exposure
                            </h5>
                        </div>
                        <div className="card-body p-0">
                            <div className="table-responsive" style={{ maxHeight: '450px' }}>
                                <table className="table table-dark table-hover mb-0 align-middle border-0">
                                    <thead>
                                        <tr className="text-muted x-small text-uppercase font-monospace">
                                            <th className="ps-4 border-0">Ticker</th>
                                            <th className="border-0">Quantity</th>
                                            <th className="border-0">Avg Cost</th>
                                            <th className="pe-4 text-end border-0">Market Value</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {positions.map((p, idx) => (
                                            <tr key={idx} className="border-bottom border-secondary border-opacity-10">
                                                <td className="ps-4 fw-bold text-white">{p.symbol}</td>
                                                <td className="font-monospace text-light">{p.qty}</td>
                                                <td className="font-monospace text-muted small">${parseFloat(p.avg_entry_price || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                                <td className="pe-4 text-end text-info font-monospace fw-bold">${parseFloat(p.market_value).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                            </tr>
                                        ))}
                                        {positions.length === 0 && (
                                            <tr><td colSpan="4" className="text-center py-5 text-muted italic">Zero active exposures in Alpaca account.</td></tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default BrokerPanel;
