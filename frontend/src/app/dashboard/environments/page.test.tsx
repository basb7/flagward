import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithIntl } from '@/test/i18n';
import EnvironmentsPage from './page';

// Mirrors the pattern in `language-switcher.test.tsx` / `create-dialogs.test.tsx`:
// mock the context hooks directly rather than mounting the real providers,
// so this test only pays for `EnvironmentsPage`'s own render logic.
// `tenantState` is mutable so each test can drive a different one of the
// page's two loading branches.
let tenantState: {
  organizations: { id: string; name: string }[];
  currentOrganization: { id: string; name: string } | null;
  currentProject: { id: string; name: string } | null;
  isLoading: boolean;
};

vi.mock('@/lib/tenant-context', () => ({
  useTenant: () => ({
    ...tenantState,
    projects: [],
    setCurrentProject: vi.fn(),
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

// Only exercised by the second case below (the first never reaches
// `loadEnvironments`'s API call, since it short-circuits on a null
// `currentProject`): never resolves, so `isLoading` stays true for the test.
vi.mock('@/lib/api', () => ({
  environmentsApi: { list: vi.fn(() => new Promise(() => {})) },
}));

describe('EnvironmentsPage loading state', () => {
  it('renders the announcing skeleton region instead of the spinner while tenant data loads', () => {
    tenantState = {
      organizations: [],
      currentOrganization: null,
      currentProject: null,
      isLoading: true,
    };
    renderWithIntl(<EnvironmentsPage />);

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Environments' }),
    ).toBeInTheDocument();
  });

  it('renders the skeleton instead of the spinner while environments load for the current project', () => {
    tenantState = {
      organizations: [{ id: 'org-1', name: 'Acme' }],
      currentOrganization: { id: 'org-1', name: 'Acme' },
      currentProject: { id: 'proj-1', name: 'Mobile' },
      isLoading: false,
    };
    renderWithIntl(<EnvironmentsPage />);

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Environments' }),
    ).toBeInTheDocument();
  });
});

describe('EnvironmentsPage without an organization', () => {
  /**
   * The call to action navigates, so it must stay a real link. Rendering a
   * Base UI Button as a Link made Base UI warn that it expected a native
   * <button>, and its `nativeButton={false}` escape hatch would announce the
   * link as a button (role="button") to assistive technology.
   */
  it('links to the overview without a Base UI native-button warning', () => {
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {});
    tenantState = {
      organizations: [],
      currentOrganization: null,
      currentProject: null,
      isLoading: false,
    };
    renderWithIntl(<EnvironmentsPage />);

    expect(
      screen.getByRole('link', { name: 'Go to Overview' }),
    ).toHaveAttribute('href', '/dashboard');
    const nativeButtonWarnings = consoleError.mock.calls
      .map((args) => args.map(String).join(' '))
      .filter((message) => message.includes('nativeButton'));
    expect(nativeButtonWarnings).toEqual([]);
  });
});
