import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithIntl } from '@/test/i18n';
import DashboardPage from './page';

// Mirrors the pattern in `environments/page.test.tsx`: mock the context
// hooks directly rather than mounting the real providers, so this test only
// pays for `DashboardPage`'s own render logic. `tenantState` is mutable so
// each test can drive a different one of the page's two loading branches.
let tenantState: {
  organizations: { id: string; name: string }[];
  projects: { id: string; name: string }[];
  currentOrganization: { id: string; name: string } | null;
  currentProject: { id: string; name: string } | null;
  isLoading: boolean;
};

vi.mock('@/lib/tenant-context', () => ({
  useTenant: () => ({
    ...tenantState,
    setCurrentOrganization: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ user: null }),
  hasOrgCapability: () => false,
}));

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

// Analytics calls never resolve so the page's own `isLoading` state (distinct
// from `isTenantLoading`) stays true for the whole test -- see the second
// case below, which depends on exactly that.
vi.mock('@/lib/api', () => ({
  environmentsApi: { list: vi.fn(() => Promise.resolve({ results: [] })) },
  analyticsApi: {
    overview: vi.fn(() => new Promise(() => {})),
    evaluationsTimeseries: vi.fn(() => new Promise(() => {})),
    topFlags: vi.fn(() => new Promise(() => {})),
  },
}));

describe('DashboardPage loading state', () => {
  it('renders the overview skeleton while tenant data loads', () => {
    tenantState = {
      organizations: [],
      projects: [],
      currentOrganization: null,
      currentProject: null,
      isLoading: true,
    };
    renderWithIntl(<DashboardPage />);

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Overview' }),
    ).toBeInTheDocument();
  });

  it('renders the overview skeleton while analytics data loads', () => {
    tenantState = {
      organizations: [{ id: 'org-1', name: 'Acme' }],
      projects: [{ id: 'proj-1', name: 'Mobile' }],
      currentOrganization: { id: 'org-1', name: 'Acme' },
      currentProject: { id: 'proj-1', name: 'Mobile' },
      isLoading: false,
    };
    renderWithIntl(<DashboardPage />);

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Overview' }),
    ).toBeInTheDocument();
  });
});
