import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  authApi: {
    me: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
  },
  onSessionExpired: vi.fn(() => () => {}),
  tenancyApi: {
    organizations: vi.fn(),
    projects: vi.fn(),
  },
}));

import {
  authApi,
  type Organization,
  onSessionExpired,
  type Project,
  tenancyApi,
} from '@/lib/api';
import { AuthProvider, hasOrgCapability, useAuth } from '@/lib/auth-context';
import { TenantProvider, useTenant } from '@/lib/tenant-context';

const me = vi.mocked(authApi.me);
const sessionExpired = vi.mocked(onSessionExpired);
const listOrganizations = vi.mocked(tenancyApi.organizations);
const listProjects = vi.mocked(tenancyApi.projects);

function organization(id: string, name = id): Organization {
  return { id, name, plan: 'COMMUNITY', created_at: '2026-01-01T00:00:00Z' };
}

function project(id: string, organizationId: string): Project {
  return {
    id,
    organization: organizationId,
    name: id,
    key: id,
    created_at: '2026-01-01T00:00:00Z',
  };
}

function page<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results };
}

function profile(organizations: { id: string; capabilities: string[] }[]) {
  return { id: 1, username: 'ada', email: 'ada@example.com', organizations };
}

beforeEach(() => {
  window.localStorage.clear();
  me.mockReset();
  sessionExpired.mockReset();
  sessionExpired.mockReturnValue(() => {});
  listOrganizations.mockReset();
  listProjects.mockReset();
  me.mockResolvedValue(profile([{ id: 'org-1', capabilities: [] }]));
  listOrganizations.mockResolvedValue(page([organization('org-1')]));
  listProjects.mockResolvedValue(page([project('proj-1', 'org-1')]));
});

/** Renders the tenant state plus the capability the nav actually gates on. */
function TenantProbe() {
  const { user } = useAuth();
  const {
    organizations,
    projects,
    currentOrganization,
    currentProject,
    isLoading,
    refresh,
    setCurrentOrganization,
  } = useTenant();

  return (
    <div>
      <span data-testid="loading">{isLoading ? 'loading' : 'ready'}</span>
      <span data-testid="organizations">
        {organizations.map((item) => item.id).join(',')}
      </span>
      <span data-testid="projects">
        {projects.map((item) => item.id).join(',')}
      </span>
      <span data-testid="current-organization">
        {currentOrganization?.id ?? 'none'}
      </span>
      <span data-testid="current-project">{currentProject?.id ?? 'none'}</span>
      <span data-testid="can-manage">
        {String(
          hasOrgCapability(user, currentOrganization?.id ?? null, 'org.manage'),
        )}
      </span>
      <button type="button" onClick={() => refresh()}>
        refresh
      </button>
      <button
        type="button"
        onClick={() => setCurrentOrganization(organization('org-2'))}
      >
        switch to org-2
      </button>
    </div>
  );
}

function renderTenant() {
  return render(
    <AuthProvider>
      <TenantProvider>
        <TenantProbe />
      </TenantProvider>
    </AuthProvider>,
  );
}

/**
 * `isLoading` starts out false for a signed-out visitor, so waiting on it
 * alone would return before `/auth/me/` has even resolved. Wait for the
 * tenancy fetch the resolved user triggers, then for loading to settle.
 */
async function renderReadyTenant() {
  const result = renderTenant();
  await waitFor(() => expect(listOrganizations).toHaveBeenCalled());
  await waitFor(() =>
    expect(screen.getByTestId('loading')).toHaveTextContent('ready'),
  );
  return result;
}

describe('TenantProvider', () => {
  it('loads organizations and projects once the user resolves', async () => {
    await renderReadyTenant();

    expect(screen.getByTestId('organizations')).toHaveTextContent('org-1');
    expect(screen.getByTestId('current-organization')).toHaveTextContent(
      'org-1',
    );
    expect(screen.getByTestId('current-project')).toHaveTextContent('proj-1');
  });

  it('never lists a project belonging to another organization', async () => {
    // The tenancy invariant, at the one place the dashboard could break it:
    // `projects` is what the project switcher renders.
    listOrganizations.mockResolvedValue(
      page([organization('org-1'), organization('org-2')]),
    );
    listProjects.mockResolvedValue(
      page([project('proj-1', 'org-1'), project('proj-foreign', 'org-2')]),
    );

    await renderReadyTenant();

    expect(screen.getByTestId('projects')).toHaveTextContent('proj-1');
    expect(screen.getByTestId('projects')).not.toHaveTextContent(
      'proj-foreign',
    );
  });

  it('drops a stored project that belongs to a different organization', async () => {
    // A stale localStorage id from a previous session must not show one
    // organization's data under another's name.
    window.localStorage.setItem('flagward.currentOrganizationId', 'org-1');
    window.localStorage.setItem('flagward.currentProjectId', 'proj-foreign');
    listOrganizations.mockResolvedValue(
      page([organization('org-1'), organization('org-2')]),
    );
    listProjects.mockResolvedValue(
      page([project('proj-1', 'org-1'), project('proj-foreign', 'org-2')]),
    );

    await renderReadyTenant();

    expect(screen.getByTestId('current-project')).toHaveTextContent('proj-1');
  });

  it('moves the current project when the organization is switched', async () => {
    listOrganizations.mockResolvedValue(
      page([organization('org-1'), organization('org-2')]),
    );
    listProjects.mockResolvedValue(
      page([project('proj-1', 'org-1'), project('proj-2', 'org-2')]),
    );
    await renderReadyTenant();
    expect(screen.getByTestId('current-project')).toHaveTextContent('proj-1');

    await act(async () => {
      screen.getByRole('button', { name: 'switch to org-2' }).click();
    });

    expect(screen.getByTestId('current-organization')).toHaveTextContent(
      'org-2',
    );
    expect(screen.getByTestId('current-project')).toHaveTextContent('proj-2');
  });

  it('clears everything when the session ends', async () => {
    // A stale org/project from an ended session must never survive into the
    // next one's first render.
    let expire: (() => void) | undefined;
    sessionExpired.mockImplementation((handler) => {
      expire = handler;
      return () => {};
    });
    listOrganizations.mockResolvedValue(page([organization('org-1')]));
    await renderReadyTenant();
    expect(screen.getByTestId('organizations')).toHaveTextContent('org-1');

    await act(async () => {
      expire?.();
    });

    expect(screen.getByTestId('organizations')).toBeEmptyDOMElement();
    expect(screen.getByTestId('projects')).toBeEmptyDOMElement();
    expect(screen.getByTestId('current-organization')).toHaveTextContent(
      'none',
    );
    expect(screen.getByTestId('current-project')).toHaveTextContent('none');
  });

  it('empties everything when the tenancy fetch fails', async () => {
    listOrganizations.mockRejectedValue(new Error('503'));
    await renderReadyTenant();

    expect(screen.getByTestId('organizations')).toBeEmptyDOMElement();
    expect(screen.getByTestId('current-organization')).toHaveTextContent(
      'none',
    );
  });

  /**
   * The regression this suite exists for.
   *
   * Creating an organization makes the caller its admin in the same backend
   * transaction, so the new capabilities only exist in `/auth/me/`. When
   * `refresh` fetched organizations and projects but not `/auth/me/`, the
   * switcher showed the new organization while every capability-gated
   * control stayed hidden -- the onboarding bug.
   */
  describe('refresh', () => {
    it('re-fetches capabilities, not only organizations and projects', async () => {
      await renderReadyTenant();
      const meCallsAfterMount = me.mock.calls.length;

      await act(async () => {
        screen.getByRole('button', { name: 'refresh' }).click();
      });

      expect(listOrganizations).toHaveBeenCalledTimes(2);
      expect(listProjects).toHaveBeenCalledTimes(2);
      expect(me.mock.calls.length).toBeGreaterThan(meCallsAfterMount);
    });

    it('makes a capability granted since mount visible without a remount', async () => {
      // The same thing stated as behaviour rather than as call counts: this
      // is what the person actually sees, and it is what broke.
      me.mockResolvedValue(profile([{ id: 'org-1', capabilities: [] }]));
      await renderReadyTenant();
      expect(screen.getByTestId('can-manage')).toHaveTextContent('false');

      me.mockResolvedValue(
        profile([{ id: 'org-1', capabilities: ['org.manage'] }]),
      );

      await act(async () => {
        screen.getByRole('button', { name: 'refresh' }).click();
      });

      expect(screen.getByTestId('can-manage')).toHaveTextContent('true');
    });

    it('shows an organization created since mount, together with its capabilities', async () => {
      // The full onboarding shape: a brand-new organization *and* the admin
      // capabilities that came with it, both after one refresh.
      await renderReadyTenant();
      expect(screen.getByTestId('organizations')).toHaveTextContent('org-1');
      expect(screen.getByTestId('can-manage')).toHaveTextContent('false');

      listOrganizations.mockResolvedValue(
        page([organization('org-1'), organization('org-2')]),
      );
      me.mockResolvedValue(
        profile([
          { id: 'org-1', capabilities: ['org.manage'] },
          { id: 'org-2', capabilities: ['org.manage'] },
        ]),
      );

      await act(async () => {
        screen.getByRole('button', { name: 'refresh' }).click();
      });

      expect(screen.getByTestId('organizations')).toHaveTextContent(
        'org-1,org-2',
      );
      expect(screen.getByTestId('can-manage')).toHaveTextContent('true');
    });
  });

  it('throws a named error when useTenant is used outside the provider', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() =>
      render(
        <AuthProvider>
          <TenantProbe />
        </AuthProvider>,
      ),
    ).toThrow('useTenant must be used within a TenantProvider');
    quiet.mockRestore();
  });
});
