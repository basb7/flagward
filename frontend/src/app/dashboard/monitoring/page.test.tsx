import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithIntl } from '@/test/i18n';
import MonitoringPage from './page';

// Mirrors the pattern in `environments/page.test.tsx`: mock the context
// hooks directly rather than mounting the real providers, so this test only
// pays for `MonitoringPage`'s own render logic.
vi.mock('@/lib/tenant-context', () => ({
  useTenant: () => ({ currentProject: { id: 'proj-1', name: 'Mobile' } }),
}));

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

// `sdkHealth` never resolves, so `load()`'s `Promise.all` never settles and
// the page's `isLoading` state stays true for the test. The others resolve
// immediately since they only matter for the count of calls, not this branch.
vi.mock('@/lib/api', () => ({
  environmentsApi: { list: vi.fn(() => Promise.resolve({ results: [] })) },
  analyticsApi: { sdkHealth: vi.fn(() => new Promise(() => {})) },
  sdkRegistrationsApi: { list: vi.fn(() => new Promise(() => {})) },
  evaluationsApi: { list: vi.fn(() => new Promise(() => {})) },
  overridesApi: { list: vi.fn(() => new Promise(() => {})) },
  flagsApi: { list: vi.fn(() => new Promise(() => {})) },
}));

describe('MonitoringPage loading state', () => {
  it('renders the announcing skeleton region instead of the spinner while monitoring data loads', () => {
    renderWithIntl(<MonitoringPage />);

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Monitoring' }),
    ).toBeInTheDocument();
  });
});
