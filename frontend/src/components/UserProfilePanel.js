/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - User profile panel for account details, password changes, and selected portfolio context.
 */

import React, { useState } from 'react';
import axios from 'axios';

/**
 * Displays authenticated user settings and portfolio summary data.
 * Uses /user/profile endpoints while keeping authentication state in the root dashboard.
 */
const UserProfilePanel = ({ user, portfolios = [], selectedId, activePortfolioDetails, onLogout, onUpdateUser, API_BASE }) => {
    const [profileData, setProfileData] = useState({
        full_name: user?.full_name || '',
        username: user?.username || '',
        gender: user?.gender || ''
    });
    const [passwords, setPasswords] = useState({
        current_password: '',
        new_password: '',
        confirm_password: ''
    });
    const [message, setMessage] = useState({ type: '', text: '' });
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);

    const handleProfileChange = (e) => {
        setProfileData({ ...profileData, [e.target.name]: e.target.value });
    };

    const handlePasswordChange = (e) => {
        setPasswords({ ...passwords, [e.target.name]: e.target.value });
    };

    const showMessage = (text, type = 'success') => {
        setMessage({ text, type });
        setTimeout(() => setMessage({ text: '', type: '' }), 5000);
    };

    const updateProfile = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const res = await axios.patch(`${API_BASE}/user/profile`, profileData);
            onUpdateUser(res.data);
            showMessage('Profile updated successfully.');
        } catch (err) {
            showMessage(err.response?.data?.detail || 'Failed to update profile.', 'danger');
        } finally {
            setLoading(false);
        }
    };

    const changePassword = async (e) => {
        e.preventDefault();
        if (passwords.new_password !== passwords.confirm_password) {
            return showMessage('New passwords do not match.', 'danger');
        }
        setLoading(true);
        try {
            await axios.post(`${API_BASE}/user/profile/change-password`, {
                current_password: passwords.current_password,
                new_password: passwords.new_password
            });
            showMessage('Password changed successfully.');
            setPasswords({ current_password: '', new_password: '', confirm_password: '' });
        } catch (err) {
            showMessage(err.response?.data?.detail || 'Failed to change password.', 'danger');
        } finally {
            setLoading(false);
        }
    };

    const handleAvatarUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('avatar', file); // Backend expects the field name "avatar".

        setUploading(true);
        try {
            const res = await axios.post(`${API_BASE}/user/profile/avatar`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            onUpdateUser(res.data);
            showMessage('Avatar uploaded successfully.');
        } catch (err) {
            // Ensure error detail is renderable text to avoid React crashes.
            const errorDetail = err.response?.data?.detail;
            const errorMsg = typeof errorDetail === 'string' 
                ? errorDetail 
                : (typeof errorDetail === 'object' ? JSON.stringify(errorDetail) : 'Failed to upload avatar.');
            showMessage(errorMsg, 'danger');
        } finally {
            setUploading(false);
        }
    };

    // Resolve relative avatar paths against the backend origin.
    const getAvatarUrl = () => {
        if (user?.avatar_url) {
            // Check if it's a full URL or relative
            if (user.avatar_url.startsWith('http')) return user.avatar_url;
            return `${API_BASE.replace('/api/v1', '')}${user.avatar_url}`;
        }
        return null;
    };

    const avatarUrl = getAvatarUrl();

    return (
        <div className="user-profile-panel p-4">
            {message.text && (
                <div className={`alert alert-${message.type} glassmorphism mb-4 fade show d-flex align-items-center`}>
                    <div className="me-2">{message.type === 'success' ? '✅' : '❌'}</div>
                    {message.text}
                </div>
            )}

            <div className="row g-4">
                {/* Summary and avatar upload controls. */}
                <div className="col-md-4">
                    <div className="card glassmorphism p-4 h-100 text-center">
                        <div className="position-relative d-inline-block mx-auto mb-3">
                            <div className="avatar-circle overflow-hidden internal-lg border border-primary" style={{ 
                                width: '120px', 
                                height: '120px', 
                                borderRadius: '50%', 
                                background: 'linear-gradient(45deg, #1a1a1a, #333)', 
                                display: 'flex', 
                                alignItems: 'center', 
                                justifyContent: 'center', 
                                fontSize: '3rem', 
                                fontWeight: 'bold', 
                                color: 'white' 
                            }}>
                                {avatarUrl ? (
                                    <img src={avatarUrl} alt="Avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                ) : (
                                    (user ? (user.full_name || user.username || '?').charAt(0).toUpperCase() : '?')
                                )}
                            </div>
                            <label className="position-absolute bottom-0 end-0 bg-primary rounded-circle p-2 internal-sm border border-dark cursor-pointer" style={{ cursor: 'pointer' }}>
                                <input type="file" hidden accept="image/*" onChange={handleAvatarUpload} disabled={uploading} />
                                {uploading ? (
                                    <span className="spinner-border spinner-border-sm text-white" role="status"></span>
                                ) : (
                                    <svg width="16" height="16" fill="white" viewBox="0 0 16 16"><path d="M10.5 8.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z"/><path d="M2 4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-1.172a2 2 0 0 1-1.414-.586l-.828-.828A2 2 0 0 0 9.172 2H6.828a2 2 0 0 0-1.414.586l-.828.828A2 2 0 0 1 3.172 4H2zm.5 2a.5.5 0 1 1 0-1 .5.5 0 0 1 0 1zm9 2.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0z"/></svg>
                                )}
                            </label>
                        </div>
                        
                        <h3 className="text-white mb-1">{user ? user.full_name : 'Guest User'}</h3>
                        <p className="text-primary fw-bold mb-3">{user ? user.email : 'No email available'}</p>
                        <div className="badge bg-dark border border-primary text-primary px-3 py-2 mb-4">ROLE: {user ? user.role : 'GUEST'}</div>
                        
                        <div className="text-start p-3 border rounded bg-dark border-secondary mb-4">
                            <div className="small text-muted text-uppercase mb-2">System Access</div>
                            <div className="d-flex justify-content-between mb-1">
                                <span className="text-muted small">Status:</span>
                                <span className="text-success small fw-bold">ACTIVE</span>
                            </div>
                            <div className="d-flex justify-content-between">
                                <span className="text-muted small">ID:</span>
                                <span className="text-info small">{user?.id?.toString().slice(0, 8)}...</span>
                            </div>
                        </div>

                        <button className="btn btn-outline-danger w-100 mt-auto" onClick={onLogout}>Sign Out Session</button>
                    </div>
                </div>

                {/* Editable profile and password forms. */}
                <div className="col-md-8">
                    <div className="card glassmorphism p-4 mb-4">
                        <h4 className="text-primary mb-4 d-flex align-items-center">
                            <svg className="me-2" width="24" height="24" fill="currentColor" viewBox="0 0 16 16"><path d="M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm2-3a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm4 8c0 1-1 1-1 1H3s-1 0-1-1 1-4 6-4 6 3 6 4zm-1-.004c-.001-.246-.154-.986-.832-1.664C11.516 10.68 10.289 10 8 10c-2.29 0-3.516.68-4.168 1.332-.678.678-.83 1.418-.832 1.664h10z"/></svg>
                            Profile Information
                        </h4>
                        
                        <form onSubmit={updateProfile}>
                            <div className="row g-3">
                                <div className="col-md-6">
                                    <label className="form-label text-muted small text-uppercase">Full Name</label>
                                    <input type="text" name="full_name" className="form-control bg-dark text-white border-secondary" value={profileData.full_name} onChange={handleProfileChange} required />
                                </div>
                                <div className="col-md-6">
                                    <label className="form-label text-muted small text-uppercase">Username</label>
                                    <input type="text" name="username" className="form-control bg-dark text-white border-secondary" value={profileData.username} onChange={handleProfileChange} required />
                                </div>
                                <div className="col-md-6">
                                    <label className="form-label text-muted small text-uppercase">Gender</label>
                                    <select name="gender" className="form-select bg-dark text-white border-secondary" value={profileData.gender} onChange={handleProfileChange}>
                                        <option value="">Select Gender</option>
                                        <option value="Male">Male</option>
                                        <option value="Female">Female</option>
                                        <option value="Other">Other</option>
                                        <option value="Prefer not to say">Prefer not to say</option>
                                    </select>
                                </div>
                                <div className="col-md-12 mt-4">
                                    <button type="submit" className="btn btn-primary px-4" disabled={loading}>
                                        {loading ? <span className="spinner-border spinner-border-sm me-2"></span> : null}
                                        Update Profile
                                    </button>
                                </div>
                            </div>
                        </form>
                    </div>

                    <div className="card glassmorphism p-4">
                        <h4 className="text-warning mb-4 d-flex align-items-center">
                            <svg className="me-2" width="24" height="24" fill="currentColor" viewBox="0 0 16 16"><path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8zm8-7a7 7 0 0 0-5.468 11.37C3.242 11.226 4.805 10 8 10s4.757 1.225 5.468 2.37A7 7 0 0 0 8 1z"/></svg>
                            Security & Credentials
                        </h4>
                        
                        <form onSubmit={changePassword}>
                            <div className="row g-3">
                                <div className="col-md-12">
                                    <label className="form-label text-muted small text-uppercase">Current Password</label>
                                    <input type="password" name="current_password" className="form-control bg-dark text-white border-secondary" value={passwords.current_password} onChange={handlePasswordChange} required />
                                </div>
                                <div className="col-md-6">
                                    <label className="form-label text-muted small text-uppercase">New Password</label>
                                    <input type="password" name="new_password" className="form-control bg-dark text-white border-secondary" value={passwords.new_password} onChange={handlePasswordChange} required minLength="8" />
                                </div>
                                <div className="col-md-6">
                                    <label className="form-label text-muted small text-uppercase">Confirm New Password</label>
                                    <input type="password" name="confirm_password" className="form-control bg-dark text-white border-secondary" value={passwords.confirm_password} onChange={handlePasswordChange} required minLength="8" />
                                </div>
                                <div className="col-md-12 mt-4">
                                    <button type="submit" className="btn btn-outline-warning px-4" disabled={loading}>
                                        {loading ? <span className="spinner-border spinner-border-sm me-2"></span> : null}
                                        Change Password
                                    </button>
                                </div>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default UserProfilePanel;
