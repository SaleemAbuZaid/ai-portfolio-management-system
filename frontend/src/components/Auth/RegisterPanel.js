/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Registration form for creating dashboard users and optional role requests.
 */

import React, { useState } from 'react';
import axios from 'axios';

/**
 * Creates a user through /auth/register and starts an authenticated dashboard session.
 * The requested role field supports academic review of the admin approval flow.
 */
const RegisterPanel = ({ API_BASE, onRegisterSuccess, onSwitchToLogin }) => {
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    full_name: '',
    username: '',
    requested_role: ''
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await axios.post(`${API_BASE}/auth/register`, formData);
      const { access_token, user } = response.data;
      localStorage.setItem('apex_token', access_token);
      onRegisterSuccess(user, access_token);
    } catch (err) {
      console.error('Registration error:', err);
      setError(err.response?.data?.detail || 'Registration failed. Try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container glass-morphism">
      <div className="auth-card">
        <h2 className="auth-title">Create Account</h2>
        <p className="auth-subtitle">Join the Apex AI Network</p>
        
        {error && <div className="auth-error">{error}</div>}
        
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label>Full Name</label>
            <input
              name="full_name"
              type="text"
              value={formData.full_name}
              onChange={handleChange}
              placeholder="John Doe"
              autoComplete="name"
              required
            />
          </div>

          <div className="form-group">
            <label>Username</label>
            <input
              name="username"
              type="text"
              value={formData.username}
              onChange={handleChange}
              placeholder="johndoe"
              autoComplete="username"
              required
            />
          </div>

          <div className="form-group">
            <label>Email Address</label>
            <input
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              placeholder="user@example.com"
              autoComplete="email"
              required
            />
          </div>
          
          <div className="form-group">
            <label>Password</label>
            <input
              name="password"
              type="password"
              value={formData.password}
              onChange={handleChange}
              placeholder="••••••••"
              autoComplete="new-password"
              required
            />
          </div>

          <div className="form-group">
            <label>Account Type</label>
            <select name="requested_role" value={formData.requested_role} onChange={handleChange}>
              <option value="" className="text-gray-900 bg-white">Standard User</option>
              <option value="BROKER" className="text-gray-900 bg-white">Request Broker Access</option>
            </select>
          </div>
          
          <button type="submit" className="auth-button" disabled={loading}>
            {loading ? 'Creating Account...' : 'Register'}
          </button>
        </form>
        
        <div className="auth-footer">
          Already have an account? <span onClick={onSwitchToLogin}>Sign In</span>
        </div>
      </div>
    </div>
  );
};

export default RegisterPanel;
