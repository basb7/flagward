/**
 * API client for Flagward backend.
 * Uses httpOnly cookies for authentication.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const REFRESH_ENDPOINT = '/api/v1/auth/refresh/';

/**
 * Endpoints that must never trigger a refresh attempt: they either establish
 * the session or are the refresh itself, so retrying them would loop.
 */
const SESSION_ENDPOINTS = [
  '/api/v1/auth/login/',
  '/api/v1/auth/register/',
  '/api/v1/auth/logout/',
  REFRESH_ENDPOINT,
];

/** A failed response, carrying the status the caller needs to react to it. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

let sessionExpiredHandler: (() => void) | null = null;

/**
 * Register the callback fired when the session cannot be recovered, so the UI
 * can drop the user it is holding and send them back to the login page.
 */
export function onSessionExpired(handler: () => void) {
  sessionExpiredHandler = handler;
  return () => {
    if (sessionExpiredHandler === handler) {
      sessionExpiredHandler = null;
    }
  };
}

let refreshInFlight: Promise<boolean> | null = null;

/**
 * Exchange the refresh cookie for a new access cookie.
 *
 * The dashboard fires several requests at once, so a shared promise keeps a
 * burst of 401s from firing a burst of refreshes.
 */
function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE_URL}${REFRESH_ENDPOINT}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }

  return refreshInFlight;
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  allowRefresh = true,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include', // Include cookies
  });

  // The access token expires long before the refresh token does, so a 401 is
  // usually recoverable without the user noticing.
  if (
    response.status === 401 &&
    allowRefresh &&
    !SESSION_ENDPOINTS.some((path) => endpoint.startsWith(path))
  ) {
    if (await refreshSession()) {
      return request<T>(endpoint, options, false);
    }
    sessionExpiredHandler?.();
  }

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ message: 'An error occurred' }));

    // DRF returns different error formats
    let errorMessage = 'Request failed';

    if (error.detail) {
      errorMessage = error.detail;
    } else if (typeof error.error === 'string') {
      // Some endpoints (invitation accept) answer with a bare error code as
      // `{"error": "<code>"}` rather than DRF's usual `detail`/`message`
      // shape -- surface the code itself so callers can map it to copy.
      errorMessage = error.error;
    } else if (error.message) {
      errorMessage = error.message;
    } else if (typeof error === 'object') {
      const messages = Object.entries(error)
        .map(([field, msgs]) => {
          const text = Array.isArray(msgs) ? msgs.join(', ') : msgs;
          return `${field}: ${text}`;
        })
        .join('\n');
      if (messages) {
        errorMessage = messages;
      }
    }

    throw new ApiError(errorMessage, response.status);
  }

  // 204 No Content has no body to parse
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

/**
 * Serialize a params object into a query string, dropping empty values so the
 * backend never receives `?environment=` and treats it as a real filter.
 */
function buildQuery(
  params: Record<string, string | number | boolean | undefined>,
) {
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }

  const query = search.toString();
  return query ? `?${query}` : '';
}

// Auth API
export const authApi = {
  login: (username: string, password: string) =>
    request<{ user: { id: number; username: string; email: string } }>(
      '/api/v1/auth/login/',
      {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      },
    ),

  register: (username: string, email: string, password: string) =>
    request<{ user: { id: number; username: string; email: string } }>(
      '/api/v1/auth/register/',
      {
        method: 'POST',
        body: JSON.stringify({ username, email, password }),
      },
    ),

  logout: () =>
    request<{ message: string }>('/api/v1/auth/logout/', {
      method: 'POST',
    }),

  me: () =>
    request<{
      id: number;
      username: string;
      email: string;
      /**
       * The caller's resolved capabilities, per organization it belongs to
       * (answered through the same `resolve_capabilities` function
       * enforcement uses -- see `authentication/views.py`). An organization
       * absent from this list is one the caller holds no membership in.
       */
      organizations: { id: string; capabilities: string[] }[];
    }>('/api/v1/auth/me/'),

  refresh: () =>
    request<{ message: string }>('/api/v1/auth/refresh/', {
      method: 'POST',
    }),

  getConfig: () =>
    request<{ password_reset_enabled: boolean }>('/api/v1/auth/config/'),

  passwordResetRequest: (email: string) =>
    request<{ detail: string }>('/api/v1/auth/password-reset/request/', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  passwordResetConfirm: (token: string, password: string) =>
    request<{ detail: string }>('/api/v1/auth/password-reset/confirm/', {
      method: 'POST',
      body: JSON.stringify({ token, password }),
    }),
};

// Projects API (read-only here: creating/moving a Project is out of scope
// for this fix; this is only enough surface for the environment-creation
// dialog below to pick a `project` to create into.)
export interface Project {
  id: string;
  organization: string;
  name: string;
  key: string;
  created_at: string;
}

export const projectsApi = {
  list: () => request<PaginatedResponse<Project>>('/api/v1/tenancy/projects/'),
};

// Environments API
export interface Environment {
  id: string;
  name: string;
  key: string;
  api_key: string;
  project: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const environmentsApi = {
  list: (params: { page?: number; project?: string } = {}) =>
    request<PaginatedResponse<Environment>>(
      `/api/v1/environments/${buildQuery({ page: params.page ?? 1, project: params.project })}`,
    ),

  get: (id: string) => request<Environment>(`/api/v1/environments/${id}/`),

  create: (data: { name: string; key: string; project: string }) =>
    request<Environment>('/api/v1/environments/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<Environment>) =>
    request<Environment>(`/api/v1/environments/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/api/v1/environments/${id}/`, {
      method: 'DELETE',
    }),
};

// Feature Flags API
export interface ActiveOverride {
  id: string;
  is_enabled: boolean;
  reason: string;
  created_at: string;
}

export interface FeatureFlag {
  id: string;
  environment: string;
  key: string;
  name: string;
  description: string;
  /** The configured state. An active override can make this differ from what SDKs see. */
  is_enabled: boolean;
  /** What SDKs actually serve: the override's value while one is active. */
  effective_is_enabled: boolean;
  active_override: ActiveOverride | null;
  flag_type: 'BOOLEAN' | 'MULTIVARIATE';
  rules: StrategyRule[];
}

export interface StrategyRule {
  id: string;
  priority: number;
  operator_logic: 'AND' | 'OR';
  conditions: Condition[];
}

export interface Condition {
  id: string;
  attribute: string;
  operator: string;
  value: unknown;
}

export const flagsApi = {
  list: (params: { page?: number; project?: string } = {}) =>
    request<PaginatedResponse<FeatureFlag>>(
      `/api/v1/flags/${buildQuery({ page: params.page ?? 1, project: params.project })}`,
    ),

  get: (id: string) => request<FeatureFlag>(`/api/v1/flags/${id}/`),

  create: (data: {
    environment: string;
    key: string;
    name: string;
    description?: string;
  }) =>
    request<FeatureFlag>('/api/v1/flags/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<FeatureFlag>) =>
    request<FeatureFlag>(`/api/v1/flags/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/api/v1/flags/${id}/`, {
      method: 'DELETE',
    }),
};

// Strategy Rules API
export interface StrategyRuleCreate {
  flag: string;
  priority: number;
  operator_logic: 'AND' | 'OR';
}

export const rulesApi = {
  list: (flagId?: string) => {
    const params = flagId ? `?flag=${flagId}` : '';
    return request<PaginatedResponse<StrategyRule>>(`/api/v1/rules/${params}`);
  },

  get: (id: string) => request<StrategyRule>(`/api/v1/rules/${id}/`),

  create: (data: StrategyRuleCreate) =>
    request<StrategyRule>('/api/v1/rules/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<StrategyRule>) =>
    request<StrategyRule>(`/api/v1/rules/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/api/v1/rules/${id}/`, {
      method: 'DELETE',
    }),
};

// Conditions API
export interface ConditionCreate {
  rule: string;
  attribute: string;
  operator: string;
  value: unknown;
}

export const conditionsApi = {
  list: (ruleId?: string) => {
    const params = ruleId ? `?rule=${ruleId}` : '';
    return request<PaginatedResponse<Condition>>(
      `/api/v1/conditions/${params}`,
    );
  },

  get: (id: string) => request<Condition>(`/api/v1/conditions/${id}/`),

  create: (data: ConditionCreate) =>
    request<Condition>('/api/v1/conditions/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<Condition>) =>
    request<Condition>(`/api/v1/conditions/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/api/v1/conditions/${id}/`, {
      method: 'DELETE',
    }),
};

// Flag Overrides API (append-only audit trail / kill switch)
export interface FlagOverride {
  id: string;
  flag: string;
  flag_key: string;
  flag_name: string;
  environment: string;
  environment_key: string;
  is_enabled: boolean;
  /** False once lifted. A lifted override stays in the trail but stops forcing. */
  is_active: boolean;
  reason: string;
  created_at: string;
  cleared_at: string | null;
}

export interface FlagOverrideCreate {
  flag: string;
  is_enabled: boolean;
  reason: string;
}

export const overridesApi = {
  list: (
    params: {
      flag?: string;
      environment?: string;
      active?: boolean;
      page?: number;
    } = {},
  ) =>
    request<PaginatedResponse<FlagOverride>>(
      `/api/v1/overrides/${buildQuery(params)}`,
    ),

  get: (id: string) => request<FlagOverride>(`/api/v1/overrides/${id}/`),

  create: (data: FlagOverrideCreate) =>
    request<FlagOverride>('/api/v1/overrides/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  /** Stop forcing the flag. The row stays in the trail, stamped as lifted. */
  lift: (id: string) =>
    request<FlagOverride>(`/api/v1/overrides/${id}/lift/`, {
      method: 'POST',
    }),
};

// SDK Registrations API (read-only: written by the SDK surface)
export type SDKType = 'PYTHON' | 'JAVASCRIPT' | 'GO';

export interface SDKRegistration {
  id: string;
  environment: string;
  environment_key: string;
  environment_name: string;
  sdk_type: SDKType;
  sdk_key: string;
  version: string;
  last_seen_at: string;
  created_at: string;
}

export const sdkRegistrationsApi = {
  list: (
    params: { environment?: string; sdk_type?: SDKType; page?: number } = {},
  ) =>
    request<PaginatedResponse<SDKRegistration>>(
      `/api/v1/sdk-registrations/${buildQuery(params)}`,
    ),
};

// Evaluation Logs API (read-only)
export interface EvaluationLog {
  id: string;
  flag: string;
  flag_key: string;
  flag_name: string;
  environment: string;
  environment_key: string;
  context_hash: string;
  result: boolean;
  timestamp: string;
}

export const evaluationsApi = {
  list: (
    params: {
      flag?: string;
      environment?: string;
      result?: boolean;
      page?: number;
    } = {},
  ) =>
    request<PaginatedResponse<EvaluationLog>>(
      `/api/v1/evaluations/${buildQuery(params)}`,
    ),
};

// Analytics API
export interface AnalyticsOverview {
  generated_at: string;
  environments: { total: number };
  flags: {
    total: number;
    /** Configured state. */
    enabled: number;
    disabled: number;
    /** What SDKs serve once active overrides are applied. */
    effective_enabled: number;
    /** Flags whose effective state is being forced by an override. */
    overridden: number;
  };
  sdks: {
    total: number;
    active: number;
    stale: number;
    active_window_minutes: number;
  };
  evaluations: {
    total: number;
    last_24h: number;
    true_rate: number | null;
    true_rate_24h: number | null;
  };
  overrides: { total: number; active: number; last_24h: number };
}

export interface EvaluationBucket {
  timestamp: string;
  total: number;
  true_count: number;
  false_count: number;
}

export interface EvaluationsTimeseries {
  hours: number;
  from: string;
  to: string;
  total: number;
  buckets: EvaluationBucket[];
}

export interface TopFlag {
  flag: string;
  flag_key: string;
  flag_name: string;
  environment_key: string;
  evaluations: number;
  true_count: number;
  false_count: number;
  true_rate: number | null;
}

export interface SDKHealth {
  active_window_minutes: number;
  total: number;
  active: number;
  stale: number;
  by_type: {
    sdk_type: SDKType;
    total: number;
    active: number;
    stale: number;
  }[];
  by_version: { sdk_type: SDKType; version: string; total: number }[];
}

export const analyticsApi = {
  overview: (params: { environment?: string; project?: string } = {}) =>
    request<AnalyticsOverview>(
      `/api/v1/analytics/overview/${buildQuery(params)}`,
    ),

  evaluationsTimeseries: (
    params: { hours?: number; environment?: string; project?: string } = {},
  ) =>
    request<EvaluationsTimeseries>(
      `/api/v1/analytics/evaluations/timeseries/${buildQuery(params)}`,
    ),

  topFlags: (
    params: {
      hours?: number;
      limit?: number;
      environment?: string;
      project?: string;
    } = {},
  ) =>
    request<{ hours: number; limit: number; results: TopFlag[] }>(
      `/api/v1/analytics/flags/top/${buildQuery(params)}`,
    ),

  sdkHealth: (params: { environment?: string; project?: string } = {}) =>
    request<SDKHealth>(`/api/v1/analytics/sdks/health/${buildQuery(params)}`),
};

// Tenancy API: the organizations and projects the tenant switcher reads.
//
// Membership, role-grant and capability-preview calls belong to the members
// screen and land with it.
export type OrganizationRole = 'ADMIN' | 'USER';
export type ProjectRole = 'ADMIN' | 'EDITOR' | 'OPERATOR' | 'VIEWER';
export type EnvironmentRole = 'ADMIN' | 'EDITOR' | 'OPERATOR' | 'VIEWER';

export interface Organization {
  id: string;
  name: string;
  plan: 'COMMUNITY' | 'STARTER' | 'TEAM';
  created_at: string;
}

export interface Project {
  id: string;
  organization: string;
  name: string;
  key: string;
  created_at: string;
}

export const tenancyApi = {
  organizations: () =>
    request<PaginatedResponse<Organization>>('/api/v1/tenancy/organizations/'),

  createOrganization: (data: { name: string }) =>
    request<Organization>('/api/v1/tenancy/organizations/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  projects: () =>
    request<PaginatedResponse<Project>>('/api/v1/tenancy/projects/'),

  createProject: (data: { organization: string; name: string; key: string }) =>
    request<Project>('/api/v1/tenancy/projects/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

export interface OrganizationMembership {
  id: string;
  organization: string;
  user: number;
  /** The member's username, carried on the row so a list can name people. */
  username: string;
  role: OrganizationRole;
  created_at: string;
}

export const organizationMembershipsApi = {
  /**
   * Scoped by `org.view` on the backend, across every organization the
   * caller can see -- there is no `?organization=` filter (the viewset
   * declares none), so callers narrow to one organization client-side.
   */
  list: (params: { page?: number } = {}) =>
    request<PaginatedResponse<OrganizationMembership>>(
      `/api/v1/tenancy/organization-memberships/${buildQuery({ page: params.page ?? 1 })}`,
    ),

  updateRole: (membershipId: string, role: OrganizationRole) =>
    request<OrganizationMembership>(
      `/api/v1/tenancy/organization-memberships/${membershipId}/`,
      { method: 'PATCH', body: JSON.stringify({ role }) },
    ),

  remove: (membershipId: string) =>
    request<void>(`/api/v1/tenancy/organization-memberships/${membershipId}/`, {
      method: 'DELETE',
    }),
};

export interface ProjectMembership {
  id: string;
  project: string;
  user: number;
  /** The member's username, carried on the row so a list can name people. */
  username: string;
  role: ProjectRole;
  created_at: string;
}

export const projectMembershipsApi = {
  /** Scoped by `project.view`; no `?project=` filter exists on this viewset. */
  list: (params: { page?: number } = {}) =>
    request<PaginatedResponse<ProjectMembership>>(
      `/api/v1/tenancy/project-memberships/${buildQuery({ page: params.page ?? 1 })}`,
    ),

  create: (data: { project: string; user: number; role: ProjectRole }) =>
    request<ProjectMembership>('/api/v1/tenancy/project-memberships/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateRole: (membershipId: string, role: ProjectRole) =>
    request<ProjectMembership>(
      `/api/v1/tenancy/project-memberships/${membershipId}/`,
      { method: 'PATCH', body: JSON.stringify({ role }) },
    ),

  remove: (membershipId: string) =>
    request<void>(`/api/v1/tenancy/project-memberships/${membershipId}/`, {
      method: 'DELETE',
    }),
};

export interface EnvironmentMembership {
  id: string;
  environment: string;
  user: number;
  /** The member's username, carried on the row so a list can name people. */
  username: string;
  role: EnvironmentRole;
  created_at: string;
}

export const environmentMembershipsApi = {
  /** Scoped by `environment.view`; no `?environment=` filter exists on this viewset. */
  list: (params: { page?: number } = {}) =>
    request<PaginatedResponse<EnvironmentMembership>>(
      `/api/v1/tenancy/environment-memberships/${buildQuery({ page: params.page ?? 1 })}`,
    ),

  create: (data: {
    environment: string;
    user: number;
    role: EnvironmentRole;
  }) =>
    request<EnvironmentMembership>('/api/v1/tenancy/environment-memberships/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateRole: (membershipId: string, role: EnvironmentRole) =>
    request<EnvironmentMembership>(
      `/api/v1/tenancy/environment-memberships/${membershipId}/`,
      { method: 'PATCH', body: JSON.stringify({ role }) },
    ),

  remove: (membershipId: string) =>
    request<void>(`/api/v1/tenancy/environment-memberships/${membershipId}/`, {
      method: 'DELETE',
    }),
};

// Invitations API: single-use organization invitation links (backend #25).
export interface Invitation {
  id: string;
  organization: string;
  role: OrganizationRole;
  created_by: number | null;
  created_by_username: string | null;
  expires_at: string;
  accepted_by: number | null;
  accepted_by_username: string | null;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  status: 'accepted' | 'revoked' | 'expired' | 'pending';
}

/**
 * Only the create response carries this -- the plaintext token is never in
 * any read serializer, so if the caller loses it here, it's gone for good.
 * `link` is the same token already assembled into a clickable
 * `/invite/<token>` URL server-side (built from `FRONTEND_BASE_URL`), so
 * callers don't need to reconstruct it from `window.location.origin`.
 */
export interface InvitationWithToken extends Invitation {
  token: string;
  link: string;
}

export interface InvitationPreview {
  organization_name: string;
  role: OrganizationRole;
}

export const invitationsApi = {
  /**
   * Scoped by `org.manage_members` server-side; no `?organization=` filter
   * exists on this viewset, so callers narrow to one organization
   * client-side -- same pattern as `organizationMembershipsApi`.
   */
  list: (params: { page?: number } = {}) =>
    request<PaginatedResponse<Invitation>>(
      `/api/v1/tenancy/invitations/${buildQuery({ page: params.page ?? 1 })}`,
    ),

  create: (data: { organization: string; role: OrganizationRole }) =>
    request<InvitationWithToken>('/api/v1/tenancy/invitations/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  revoke: (id: string) =>
    request<Invitation>(`/api/v1/tenancy/invitations/${id}/revoke/`, {
      method: 'POST',
    }),

  /**
   * Public, unauthenticated. Every invalid state -- unknown, expired,
   * revoked, already used -- answers the identical generic 404 on purpose,
   * so this can never be used to probe a token.
   */
  preview: (token: string) =>
    request<InvitationPreview>(`/api/v1/tenancy/invitations/${token}/preview/`),

  /**
   * Authenticated. Distinguishable failures: 410 `invitation_revoked` /
   * `invitation_expired`, 409 `invitation_already_used` / `already_a_member`,
   * 400 `seat_limit_reached`, 404 `invitation_not_found`.
   */
  accept: (token: string) =>
    request<OrganizationMembership>(
      `/api/v1/tenancy/invitations/${token}/accept/`,
      { method: 'POST' },
    ),
};

/**
 * The mitigation for the proposal's top risk (design D10): answers what a
 * PROPOSED, unsaved set of roles would grant per environment, through the
 * exact same `resolve_capabilities` function the backend uses to enforce.
 * Nothing here is persisted.
 */
export interface EffectiveCapabilitiesPreviewRequest {
  organization: string;
  organization_role?: OrganizationRole | null;
  project_roles?: Record<string, ProjectRole>;
  environment_roles?: Record<string, EnvironmentRole>;
}

export interface EffectiveCapabilitiesPreviewEnvironment {
  id: string;
  key: string;
  capabilities: string[];
}

export const effectiveCapabilitiesApi = {
  preview: (data: EffectiveCapabilitiesPreviewRequest) =>
    request<{ environments: EffectiveCapabilitiesPreviewEnvironment[] }>(
      '/api/v1/tenancy/effective-capabilities/preview/',
      { method: 'POST', body: JSON.stringify(data) },
    ),
};
