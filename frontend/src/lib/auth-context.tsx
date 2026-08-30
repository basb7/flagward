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
 */
export function hasOrgCapability(
  user: User | null,
  organizationId: string | null | undefined,
  capability: string,
): boolean {
  if (!user || !organizationId) return false;
  return (
    user.organizations
      .find((organization) => organization.id === organizationId)
      ?.capabilities.includes(capability) ?? false
  );
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
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

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
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
