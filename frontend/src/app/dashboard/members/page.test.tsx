import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithIntl } from '@/test/i18n';

// Mirrors the pattern in `environments/page.test.tsx`: mock the context
// hooks directly rather than mounting the real providers, so this test only
// pays for `MembersPage`'s own render logic. `tenantState` is mutable so
// each test can drive a different one of the page's four loading branches.
let tenantState: {
  currentOrganization: { id: string; name: string } | null;
  projects: { id: string; name: string }[];
  currentProject: { id: string; name: string } | null;
  isLoading: boolean;
};

vi.mock('@/lib/tenant-context', () => ({
  useTenant: () => tenantState,
}));

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@/lib/error-copy', () => ({
  useErrorCopy: () => (code: string) => code,
}));

vi.mock('@/lib/api', () => ({
  organizationMembershipsApi: { list: vi.fn() },
  invitationsApi: { list: vi.fn() },
  environmentsApi: { list: vi.fn() },
  projectMembershipsApi: { list: vi.fn() },
  environmentMembershipsApi: { list: vi.fn() },
  effectiveCapabilitiesApi: { preview: vi.fn() },
}));

import {
  environmentMembershipsApi,
  environmentsApi,
  invitationsApi,
  organizationMembershipsApi,
  projectMembershipsApi,
} from '@/lib/api';
import MembersPage from './page';

const listOrgMembers = vi.mocked(organizationMembershipsApi.list);
const listInvitations = vi.mocked(invitationsApi.list);
const listEnvironments = vi.mocked(environmentsApi.list);
const listProjectMemberships = vi.mocked(projectMembershipsApi.list);
const listEnvironmentMemberships = vi.mocked(environmentMembershipsApi.list);

// Resolves immediately, for whichever section a given test is not targeting.
const emptyList = () =>
  Promise.resolve({ results: [], count: 0, next: null, previous: null });
// Never resolves, so the section relying on it stays in its loading state
// for the whole test.
const neverResolves = () => new Promise<never>(() => {});

beforeEach(() => {
  listOrgMembers.mockReset().mockImplementation(emptyList);
  listInvitations.mockReset().mockImplementation(emptyList);
  listEnvironments.mockReset().mockImplementation(emptyList);
  listProjectMemberships.mockReset().mockImplementation(emptyList);
  listEnvironmentMemberships.mockReset().mockImplementation(emptyList);
});

describe('MembersPage loading state', () => {
  it('renders the whole-page skeleton while tenant data loads', () => {
    tenantState = {
      currentOrganization: null,
      projects: [],
      currentProject: null,
      isLoading: true,
    };
    renderWithIntl(<MembersPage />);

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Members' }),
    ).toBeInTheDocument();
  });

  it('renders the members table skeleton while organization members load', async () => {
    tenantState = {
      currentOrganization: { id: 'org-1', name: 'Acme' },
      projects: [],
      currentProject: null,
      isLoading: false,
    };
    listOrgMembers.mockImplementation(neverResolves);

    renderWithIntl(<MembersPage />);

    // Wait for the invitations section (which resolves immediately) to
    // settle on its resolved, non-loading text -- confirming the one
    // `status` region left standing is the members table this test targets,
    // rather than a transient loading state some other section briefly
    // passes through on its way to resolving.
    await screen.findByText('No pending invitations');
    expect(
      screen.getByRole('status', { name: 'Loading organization members' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
  });

  it('renders the invitations table skeleton while invitations load', async () => {
    tenantState = {
      currentOrganization: { id: 'org-1', name: 'Acme' },
      projects: [],
      currentProject: null,
      isLoading: false,
    };
    listInvitations.mockImplementation(neverResolves);

    renderWithIntl(<MembersPage />);

    // Wait for the members section (which resolves immediately) to settle,
    // for the same reason as above.
    await screen.findByText('No members yet');
    expect(
      screen.getByRole('status', { name: 'Loading pending invitations' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
  });

  it('renders the grants table skeleton while project grants load', async () => {
    tenantState = {
      currentOrganization: { id: 'org-1', name: 'Acme' },
      projects: [],
      currentProject: { id: 'proj-1', name: 'Mobile' },
      isLoading: false,
    };
    listEnvironments.mockImplementation(neverResolves);

    renderWithIntl(<MembersPage />);

    // Wait for both the members and invitations sections (which resolve
    // immediately) to settle, for the same reason as above.
    await screen.findByText('No members yet');
    await screen.findByText('No pending invitations');
    expect(
      screen.getByRole('status', { name: 'Loading grants' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
  });
});
