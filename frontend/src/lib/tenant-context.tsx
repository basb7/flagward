'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { type Organization, type Project, tenancyApi } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

const CURRENT_PROJECT_STORAGE_KEY = 'flagward.currentProjectId';

interface TenantContextType {
  organizations: Organization[];
  projects: Project[];
  currentOrganization: Organization | null;
  currentProject: Project | null;
  setCurrentProject: (project: Project | null) => void;
  isLoading: boolean;
}

const TenantContext = createContext<TenantContextType | undefined>(undefined);

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [organizationsRes, projectsRes] = await Promise.all([
        tenancyApi.organizations(),
        tenancyApi.projects(),
      ]);
      setOrganizations(organizationsRes.results);
      setProjects(projectsRes.results);

      const stored = window.localStorage.getItem(CURRENT_PROJECT_STORAGE_KEY);
      const restored = projectsRes.results.find(
        (project) => project.id === stored,
      );
      setCurrentProjectId(restored?.id ?? projectsRes.results[0]?.id ?? null);
    } catch {
      setOrganizations([]);
      setProjects([]);
      setCurrentProjectId(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user) {
      // Signed out (or not yet resolved): drop everything so a stale
      // org/project from a previous session never leaks into the next one's
      // first render.
      setOrganizations([]);
      setProjects([]);
      setCurrentProjectId(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    load();
  }, [user, load]);

  const currentProject = useMemo(
    () => projects.find((project) => project.id === currentProjectId) ?? null,
    [projects, currentProjectId],
  );

  const currentOrganization = useMemo(() => {
    if (currentProject) {
      return (
        organizations.find(
          (organization) => organization.id === currentProject.organization,
        ) ?? null
      );
    }
    return organizations[0] ?? null;
  }, [organizations, currentProject]);

  const setCurrentProject = useCallback((project: Project | null) => {
    setCurrentProjectId(project?.id ?? null);
    if (project) {
      window.localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, project.id);
    } else {
      window.localStorage.removeItem(CURRENT_PROJECT_STORAGE_KEY);
    }
  }, []);

  return (
    <TenantContext.Provider
      value={{
        organizations,
        projects,
        currentOrganization,
        currentProject,
        setCurrentProject,
        isLoading,
      }}
    >
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant() {
  const context = useContext(TenantContext);
  if (context === undefined) {
    throw new Error('useTenant must be used within a TenantProvider');
  }
  return context;
}
