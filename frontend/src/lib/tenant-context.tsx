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

const CURRENT_ORGANIZATION_STORAGE_KEY = 'flagward.currentOrganizationId';
const CURRENT_PROJECT_STORAGE_KEY = 'flagward.currentProjectId';

interface TenantContextType {
  organizations: Organization[];
  /** Projects belonging to `currentOrganization` only -- never a foreign one. */
  projects: Project[];
  currentOrganization: Organization | null;
  currentProject: Project | null;
  /**
   * Switches organizations. The current project moves to the new
   * organization's first project, or to none, so the UI never shows one
   * organization's data under another's name.
   */
  setCurrentOrganization: (organization: Organization | null) => void;
  setCurrentProject: (project: Project | null) => void;
  isLoading: boolean;
  /**
   * Re-fetches organizations and projects, e.g. after creating, renaming or
   * deleting one -- and, alongside that, `/auth/me/`'s per-organization
   * capabilities. The two only ever change together (a new organization or
   * membership is also a new capability set), so one `refresh` keeps both in
   * sync instead of leaving call sites to remember which mutation needs which
   * fetch.
   */
  refresh: () => Promise<void>;
}

const TenantContext = createContext<TenantContextType | undefined>(undefined);

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const { user, refreshCapabilities } = useAuth();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [allProjects, setAllProjects] = useState<Project[]>([]);
  const [currentOrganizationId, setCurrentOrganizationId] = useState<
    string | null
  >(null);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [organizationsRes, projectsRes] = await Promise.all([
        tenancyApi.organizations(),
        tenancyApi.projects(),
      ]);
      setOrganizations(organizationsRes.results);
      setAllProjects(projectsRes.results);

      const storedOrganizationId = window.localStorage.getItem(
        CURRENT_ORGANIZATION_STORAGE_KEY,
      );
      const restoredOrganization =
        organizationsRes.results.find(
          (organization) => organization.id === storedOrganizationId,
        ) ?? organizationsRes.results[0];
      const resolvedOrganizationId = restoredOrganization?.id ?? null;
      setCurrentOrganizationId(resolvedOrganizationId);

      // A project only counts as restorable when it still belongs to the
      // organization we just resolved -- otherwise a stale localStorage
      // project id would show one organization's data under another's name.
      const storedProjectId = window.localStorage.getItem(
        CURRENT_PROJECT_STORAGE_KEY,
      );
      const projectsInOrganization = projectsRes.results.filter(
        (project) => project.organization === resolvedOrganizationId,
      );
      const restoredProject =
        projectsInOrganization.find(
          (project) => project.id === storedProjectId,
        ) ?? projectsInOrganization[0];
      setCurrentProjectId(restoredProject?.id ?? null);
    } catch {
      setOrganizations([]);
      setAllProjects([]);
      setCurrentOrganizationId(null);
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
      setAllProjects([]);
      setCurrentOrganizationId(null);
      setCurrentProjectId(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    load();
  }, [user, load]);

  // The public `refresh` (see the interface doc above): re-runs `load` and
  // `refreshCapabilities` together. Deliberately not folded into the
  // mount/user-change effect above -- `refreshCapabilities` replaces `user`
  // with a new object every call, and that effect depends on `user`, so
  // calling it from inside would re-trigger the effect on every refresh.
  const refresh = useCallback(async () => {
    await Promise.all([load(), refreshCapabilities()]);
  }, [load, refreshCapabilities]);

  const currentOrganization = useMemo(
    () =>
      organizations.find(
        (organization) => organization.id === currentOrganizationId,
      ) ?? null,
    [organizations, currentOrganizationId],
  );

  const projects = useMemo(
    () =>
      currentOrganization
        ? allProjects.filter(
            (project) => project.organization === currentOrganization.id,
          )
        : [],
    [allProjects, currentOrganization],
  );

  const currentProject = useMemo(
    () =>
      allProjects.find((project) => project.id === currentProjectId) ?? null,
    [allProjects, currentProjectId],
  );

  const persistProject = useCallback((project: Project | null) => {
    setCurrentProjectId(project?.id ?? null);
    if (project) {
      window.localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, project.id);
    } else {
      window.localStorage.removeItem(CURRENT_PROJECT_STORAGE_KEY);
    }
  }, []);

  const setCurrentProject = useCallback(
    (project: Project | null) => {
      persistProject(project);
    },
    [persistProject],
  );

  const setCurrentOrganization = useCallback(
    (organization: Organization | null) => {
      setCurrentOrganizationId(organization?.id ?? null);
      if (organization) {
        window.localStorage.setItem(
          CURRENT_ORGANIZATION_STORAGE_KEY,
          organization.id,
        );
      } else {
        window.localStorage.removeItem(CURRENT_ORGANIZATION_STORAGE_KEY);
      }

      // The current project belongs to the old organization: move to the new
      // organization's first project, or to none, rather than leaving a
      // foreign project selected.
      const nextProject = organization
        ? (allProjects.find(
            (project) => project.organization === organization.id,
          ) ?? null)
        : null;
      persistProject(nextProject);
    },
    [allProjects, persistProject],
  );

  return (
    <TenantContext.Provider
      value={{
        organizations,
        projects,
        currentOrganization,
        currentProject,
        setCurrentOrganization,
        setCurrentProject,
        isLoading,
        refresh,
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
