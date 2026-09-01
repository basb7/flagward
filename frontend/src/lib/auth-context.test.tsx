import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The network boundary. Everything below tests the context's own logic
// against a controlled `/auth/me/` answer -- no MSW, no real fetch.
vi.mock('@/lib/api', () => ({
  authApi: {
    me: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
  },
  onSessionExpired: vi.fn(() => () => {}),
}));

import { authApi, onSessionExpired } from '@/lib/api';
import { AuthProvider, hasOrgCapability, useAuth } from '@/lib/auth-context';

const me = vi.mocked(authApi.me);
const login = vi.mocked(authApi.login);
const logout = vi.mocked(authApi.logout);
const sessionExpired = vi.mocked(onSessionExpired);

/** A `/auth/me/` answer, with whatever capabilities the test needs. */
function profile(organizations: { id: string; capabilities: string[] }[]) {
  return {
    id: 1,
    username: 'ada',
    email: 'ada@example.com',
    organizations,
  };
}

beforeEach(() => {
  me.mockReset();
  login.mockReset();
  logout.mockReset();
  sessionExpired.mockReset();
  sessionExpired.mockReturnValue(() => {});
});

/**
 * `hasOrgCapability` decides which buttons each person sees. It is a pure
 * function over what `/auth/me/` answered, so it is tested directly rather
 * than through a rendered tree -- but it is the closest thing the dashboard
 * has to an authorization check, so it is tested exhaustively.
 */
describe('hasOrgCapability', () => {
  const user = profile([
    { id: 'org-1', capabilities: ['org.manage', 'org.delete'] },
    { id: 'org-2', capabilities: ['flag.read'] },
  ]);

  it('grants a capability the user holds in that organization', () => {
    expect(hasOrgCapability(user, 'org-1', 'org.manage')).toBe(true);
    expect(hasOrgCapability(user, 'org-1', 'org.delete')).toBe(true);
    expect(hasOrgCapability(user, 'org-2', 'flag.read')).toBe(true);
  });

  it('refuses a capability the user does not hold in that organization', () => {
    expect(hasOrgCapability(user, 'org-1', 'flag.read')).toBe(false);
    expect(hasOrgCapability(user, 'org-2', 'org.delete')).toBe(false);
  });

  it('never leaks a capability across organizations', () => {
    // The single most dangerous mistake this function could make: holding
    // org.delete anywhere must not read as holding it everywhere.
    expect(hasOrgCapability(user, 'org-2', 'org.manage')).toBe(false);
  });

  it('refuses an organization the user holds no membership in', () => {
    // An organization absent from the list is one the caller is not a member
    // of -- the backend answers `/auth/me/` that way on purpose.
    expect(hasOrgCapability(user, 'org-someone-elses', 'org.manage')).toBe(
      false,
    );
  });

  it('refuses when there is no user yet', () => {
    // The first frame after mount, before checkAuth resolves.
    expect(hasOrgCapability(null, 'org-1', 'org.manage')).toBe(false);
  });

  it('refuses when no organization is selected', () => {
    // TenantProvider has not resolved a current organization yet, so the id
    // is null/undefined rather than a real one.
    expect(hasOrgCapability(user, null, 'org.manage')).toBe(false);
    expect(hasOrgCapability(user, undefined, 'org.manage')).toBe(false);
    expect(hasOrgCapability(user, '', 'org.manage')).toBe(false);
  });

  it('refuses an empty capability string rather than matching anything', () => {
    expect(hasOrgCapability(user, 'org-1', '')).toBe(false);
  });

  it('matches a capability name exactly, never as a prefix', () => {
    expect(hasOrgCapability(user, 'org-1', 'org.')).toBe(false);
    expect(hasOrgCapability(user, 'org-1', 'org.manage.all')).toBe(false);
    expect(hasOrgCapability(user, 'org-1', 'ORG.MANAGE')).toBe(false);
  });

  it('refuses for a user with an empty organization list', () => {
    expect(hasOrgCapability(profile([]), 'org-1', 'org.manage')).toBe(false);
  });

  it('refuses for an organization entry carrying no capabilities', () => {
    const stripped = profile([{ id: 'org-1', capabilities: [] }]);
    expect(hasOrgCapability(stripped, 'org-1', 'org.manage')).toBe(false);
  });

  /**
   * A malformed `/auth/me/` payload must fail closed, not throw.
   *
   * `organizations` arrives over the network, so its shape is an assumption,
   * not a guarantee: a partial deploy, a proxy that rewrites a body, or a
   * serializer change can all deliver something other than the declared
   * type. A thrown TypeError here unmounts the dashboard through React's
   * error boundary; returning false merely hides a button the caller may
   * well not be allowed to press anyway. For permission logic, hiding is
   * the safe answer and crashing is not.
   */
  describe('with a malformed payload', () => {
    const malformed: [string, unknown][] = [
      ['organizations missing entirely', { id: 1, username: 'ada' }],
      ['organizations null', profileWith(null)],
      ['organizations an object, not an array', profileWith({ 'org-1': [] })],
      ['organizations a string', profileWith('org-1')],
      ['an entry that is null', profileWith([null])],
      ['an entry with no capabilities key', profileWith([{ id: 'org-1' }])],
      [
        'an entry whose capabilities is null',
        profileWith([{ id: 'org-1', capabilities: null }]),
      ],
      [
        'an entry whose capabilities is a string',
        profileWith([{ id: 'org-1', capabilities: 'org.manage' }]),
      ],
    ];

    function profileWith(organizations: unknown) {
      return {
        id: 1,
        username: 'ada',
        email: 'ada@example.com',
        organizations,
      };
    }

    for (const [label, payload] of malformed) {
      it(`refuses, without throwing, when ${label}`, () => {
        expect(() =>
          hasOrgCapability(
            payload as Parameters<typeof hasOrgCapability>[0],
            'org-1',
            'org.manage',
          ),
        ).not.toThrow();
        expect(
          hasOrgCapability(
            payload as Parameters<typeof hasOrgCapability>[0],
            'org-1',
            'org.manage',
          ),
        ).toBe(false);
      });
    }
  });
});

/** Renders whatever the context currently holds, so a test can read it. */
function AuthProbe() {
  const { user, isLoading, refreshCapabilities, login: doLogin } = useAuth();
  return (
    <div>
      <span data-testid="loading">{isLoading ? 'loading' : 'ready'}</span>
      <span data-testid="username">{user?.username ?? 'anonymous'}</span>
      <span data-testid="manage">
        {String(hasOrgCapability(user, 'org-1', 'org.manage'))}
      </span>
      <button type="button" onClick={() => refreshCapabilities()}>
        refresh capabilities
      </button>
      <button type="button" onClick={() => doLogin('ada', 'pw')}>
        sign in
      </button>
    </div>
  );
}

function renderAuth() {
  return render(
    <AuthProvider>
      <AuthProbe />
    </AuthProvider>,
  );
}

describe('AuthProvider', () => {
  it('loads the profile on mount and stops loading', async () => {
    me.mockResolvedValue(
      profile([{ id: 'org-1', capabilities: ['org.manage'] }]),
    );
    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('ready'),
    );
    expect(screen.getByTestId('username')).toHaveTextContent('ada');
    expect(screen.getByTestId('manage')).toHaveTextContent('true');
  });

  it('leaves the user null when /auth/me/ rejects, and still stops loading', async () => {
    // A signed-out visitor: the route guard needs isLoading to settle,
    // otherwise the dashboard spins forever instead of redirecting.
    me.mockRejectedValue(new Error('401'));
    renderAuth();

    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('ready'),
    );
    expect(screen.getByTestId('username')).toHaveTextContent('anonymous');
  });

  it('fetches the profile after login, because the login response carries no capabilities', async () => {
    // The provider stays mounted across the navigation into the dashboard,
    // so without this fetch the first dashboard frame would believe the
    // user belongs to no organization at all.
    me.mockRejectedValueOnce(new Error('401'));
    renderAuth();
    await waitFor(() =>
      expect(screen.getByTestId('loading')).toHaveTextContent('ready'),
    );

    login.mockResolvedValue({
      user: { id: 1, username: 'ada', email: 'ada@example.com' },
    });
    me.mockResolvedValue(
      profile([{ id: 'org-1', capabilities: ['org.manage'] }]),
    );

    await act(async () => {
      screen.getByRole('button', { name: 'sign in' }).click();
    });

    expect(me).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('manage')).toHaveTextContent('true');
  });

  it('refreshCapabilities replaces the cached capabilities with what /auth/me/ answers now', async () => {
    // The production bug: capabilities were read once at mount and went
    // stale the moment a membership changed underneath them.
    me.mockResolvedValueOnce(profile([{ id: 'org-1', capabilities: [] }]));
    renderAuth();
    await waitFor(() =>
      expect(screen.getByTestId('manage')).toHaveTextContent('false'),
    );

    me.mockResolvedValueOnce(
      profile([{ id: 'org-1', capabilities: ['org.manage'] }]),
    );
    await act(async () => {
      screen.getByRole('button', { name: 'refresh capabilities' }).click();
    });

    expect(screen.getByTestId('manage')).toHaveTextContent('true');
  });

  it('keeps the current user when refreshCapabilities fails', async () => {
    // A transient network blip must not sign anyone out -- checkAuth and the
    // onSessionExpired listener own that decision, not this call.
    me.mockResolvedValueOnce(
      profile([{ id: 'org-1', capabilities: ['org.manage'] }]),
    );
    renderAuth();
    await waitFor(() =>
      expect(screen.getByTestId('username')).toHaveTextContent('ada'),
    );

    me.mockRejectedValueOnce(new Error('503'));
    await act(async () => {
      screen.getByRole('button', { name: 'refresh capabilities' }).click();
    });

    expect(screen.getByTestId('username')).toHaveTextContent('ada');
    expect(screen.getByTestId('manage')).toHaveTextContent('true');
  });

  it('drops the user when the session expires', async () => {
    // Without this the UI keeps believing it is signed in while every
    // request fails, and the redirect to /login never fires.
    me.mockResolvedValue(
      profile([{ id: 'org-1', capabilities: ['org.manage'] }]),
    );
    let expire: (() => void) | undefined;
    sessionExpired.mockImplementation((handler) => {
      expire = handler;
      return () => {};
    });

    renderAuth();
    await waitFor(() =>
      expect(screen.getByTestId('username')).toHaveTextContent('ada'),
    );

    await act(async () => {
      expire?.();
    });

    expect(screen.getByTestId('username')).toHaveTextContent('anonymous');
    expect(screen.getByTestId('manage')).toHaveTextContent('false');
  });

  it('throws a named error when useAuth is used outside the provider', () => {
    // The message is the whole value of this guard: without it the failure
    // is "cannot destructure property of undefined" somewhere else.
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<AuthProbe />)).toThrow(
      'useAuth must be used within an AuthProvider',
    );
    quiet.mockRestore();
  });
});
