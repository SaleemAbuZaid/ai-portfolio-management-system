/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Displays external finance references that support reviewer navigation during demos.
 */
import React from 'react';

const ExternalReferences = () => {
    return (
        <div className="card glassmorphism">
            <div className="card-header">
                <h5>
                    <span className="me-2">🌐</span>
                    External Market References
                </h5>
            </div>
            <div className="card-body">
                <div className="d-flex flex-column gap-3">
                    <a href="https://www.msn.com/tr-tr/finans?ocid=winp2fptaskbar&id=avytp2" 
                       target="_blank" rel="noopener noreferrer" 
                       className="text-decoration-none d-flex align-items-center" style={{ color: '#ced4da' }}>
                        <span className="me-2" style={{ color: '#00d4ff' }}>🔗</span> MSN Finans
                    </a>
                    <a href="https://finance.yahoo.com/" 
                       target="_blank" rel="noopener noreferrer" 
                       className="text-decoration-none d-flex align-items-center" style={{ color: '#ced4da' }}>
                        <span className="me-2" style={{ color: '#00d4ff' }}>🔗</span> Yahoo Finance
                    </a>
                    <a href="https://www.tradingview.com/" 
                       target="_blank" rel="noopener noreferrer" 
                       className="text-decoration-none d-flex align-items-center" style={{ color: '#ced4da' }}>
                        <span className="me-2" style={{ color: '#00d4ff' }}>🔗</span> TradingView
                    </a>
                </div>
                <div className="mt-4 pt-3 border-top border-secondary text-muted small" style={{ fontStyle: 'italic' }}>
                    These platforms are provided as external market references only. Apex AI uses its own backend APIs, Redis cache, database, and AI pipeline for analysis and recommendations.
                </div>
            </div>
        </div>
    );
};

export default ExternalReferences;
