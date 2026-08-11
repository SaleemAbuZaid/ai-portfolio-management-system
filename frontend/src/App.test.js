/*
 * Project: APEX AI Portfolio Management System
 * Course: Graduation Project / Engineering Project
 * Team Members:
 * - Saleem A. S. AbuZaid
 * - Rashad Naghdiyev
 * Advisor:
 * Prof.Dr. Selim Akyokuş
 * Description:
 * - Jest smoke test that verifies the Apex dashboard shell renders.
 */
import { render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

jest.mock('axios', () => ({
  defaults: { headers: { common: {} } },
  get: jest.fn((url) => {
    if (url.includes('/portfolio/status')) {
      return Promise.resolve({ data: { provider: 'Alpaca Paper', aum: 100000, currency: 'USD' } });
    }
    if (url.includes('/portfolio/')) return Promise.resolve({ data: [] });
    if (url.includes('/news/latest')) return Promise.resolve({ data: { articles: [], metadata: { live_count: 0, fallback_count: 0 } } });
    if (url.includes('/market/status/snapshot')) return Promise.resolve({ data: [] });
    if (url.includes('/market/history/')) return Promise.resolve({ data: [] });
    if (url.includes('/ai/recommendations/latest')) return Promise.resolve({ data: [] });
    if (url.includes('/ai/advice/overview')) return Promise.resolve({ data: [] });
    if (url.includes('/metrics/step12-validation')) return Promise.resolve({ data: { status: 'PASS' } });
    if (url.includes('/ai/model-status')) return Promise.resolve({ data: { model_name: 'XGBoost', models: { xgboost: { status: 'loaded' } } } });
    if (url.includes('/metrics/credential-health')) return Promise.resolve({ data: { status: {} } });
    if (url.includes('/metrics/step7-status')) return Promise.resolve({ data: { audit_status: 'PASSED' } });
    if (url.includes('/ai/execution-logs')) return Promise.resolve({ data: [] });
    if (url.includes('/auth/me')) return Promise.resolve({ data: { full_name: 'Test User', email: 'test@example.com', role: 'ADMIN' } });
    return Promise.resolve({ data: {} });
  }),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  delete: jest.fn(() => Promise.resolve({ data: {} })),
}));

jest.mock('react-chartjs-2', () => ({
  Line: () => <div data-testid="line-chart" />,
  Doughnut: () => <div data-testid="doughnut-chart" />,
  Pie: () => <div data-testid="pie-chart" />,
}));

const App = require('./App').default;

beforeEach(() => {
  localStorage.clear();
  jest.clearAllMocks();
});

test('renders the Apex dashboard shell', async () => {
  render(<App />);
  expect(screen.getByText(/Market Center/i)).toBeInTheDocument();
  expect(screen.getByText(/MODE:/i)).toBeInTheDocument();
  expect(screen.getByText(/AUM:/i)).toBeInTheDocument();
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/portfolio/status'), expect.anything()));
});
