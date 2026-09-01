'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { authApi, onSessionExpired } from '@/lib/api';

interface User {
  id: number;
  username: string;
  email: string;
  /** The caller's resolved capabilities, per organization it belongs to. */
  organizations: { id: string; capabilities: string[] }[];
}

/**
 * Whether `user` holds `capability` in the organization `organizationId`.
 * Reads only what `/auth/me/` already answered through `resolve_capabilities`
 * -- never re-derived here, so the dashboard cannot drift from what the
 * backend actually enforces.
 *
 * The shape checks are not defensive noise. `organizations` arrives over the
 * network, so the declared type is an assumption rather than a guarantee, and
 * reading it unchecked fails in two different ways:
 *
 * - A non-array `organizations`, or an entry with no `capabilities` array,
 *   throws a TypeError. Every caller is inside render, so that unmounts the
 *   dashboard rather than hiding one button.
 * - Worse, a `capabilities` that arrives as a *string* answers
 *   `'org.manage.all'.includes('org.manage')` with `true` -- a malformed
 *   payload silently granting a capability by substring.
 *
 * An `Array.isArray` on each level closes both: anything unrecognisable is
 * simply not a grant.
 */
export function hasOrgCapability(
  user: User | null,
  organizationId: string | null | undefined,
  capability: string,
): boolean {
  if (!user || !organizationId || !capability) return false;
  if (!Array.isArray(user.organizations)) return false;
  const organization = user.organizations.find(
    (candidate) => candidate?.id === organizationId,
  );
  if (!Array.isArray(organization?.capabilities)) return false;
  return organization.capabilities.includes(capability);
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /**
   * Re-fetches `/auth/me/` and replaces `user` with what it answers now.
   *
   * `checkAuth` only runs on mount, so anything that changes which
   * organizations the caller belongs to -- or what it can do in one --
   * without a remount (creating an organization, joining one) leaves `user`
   * stale. Call this right after such a mutation, before anything reads
   * `hasOrgCapability` against the result.
   */
  refreshCapabilities: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const userData = await authApi.me();
      setUser(userData);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // checkAuth only runs on mount, so without this the user stays in state long
  // after the cookies stop working: requests fail while the UI still believes
  // it is signed in, and the guard that redirects to /login never fires.
  useEffect(() => onSessionExpired(() => setUser(null)), []);

  const login = async (username: string, password: string) => {
    await authApi.login(username, password);
    // The login response only carries id/username/email. Capabilities come
    // from `/auth/me/`, and the provider stays mounted across this
    // navigation (no fresh `checkAuth()` on the dashboard route), so without
    // this fetch the dashboard would render its first frame believing the
    // user belongs to no organization at all.
    const profile = await authApi.me();
    setUser(profile);
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      // An expired session cannot be logged out of, but the client still has
      // to forget it.
      setUser(null);
    }
  };

  const refreshCapabilities = useCallback(async () => {
    try {
      const userData = await authApi.me();
      setUser(userData);
    } catch {
      // A transient failure here shouldn't sign anyone out -- checkAuth and
      // the onSessionExpired listener already own that decision.
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, isLoading, login, logout, refreshCapabilities }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
