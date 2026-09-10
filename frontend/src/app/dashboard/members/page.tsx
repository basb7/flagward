'use client';

import {
  Ban,
  Copy,
  Info,
  Lock,
  Mail,
  Plus,
  ShieldAlert,
  UserMinus,
  UserPlus,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { DataTableSkeleton } from '@/components/dashboard/skeletons/data-table-skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LoadingRegion } from '@/components/ui/loading-region';
import { PageHeader } from '@/components/ui/page-header';
import { Skeleton } from '@/components/ui/skeleton';
import { Spinner } from '@/components/ui/spinner';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  type EffectiveCapabilitiesPreviewEnvironment,
  type Environment,
  type EnvironmentMembership,
  type EnvironmentRole,
  effectiveCapabilitiesApi,
  environmentMembershipsApi,
  environmentsApi,
  type Invitation,
  type InvitationWithToken,
  invitationsApi,
  type OrganizationMembership,
  type OrganizationRole,
  organizationMembershipsApi,
  type ProjectMembership,
  type ProjectRole,
  projectMembershipsApi,
} from '@/lib/api';
import { useErrorCopy } from '@/lib/error-copy';
import { useTenant } from '@/lib/tenant-context';
import { useToast } from '@/lib/toast-context';
import { formatRelativeTime } from '@/lib/utils';

/**
 * The Members screen never renders a checkbox grid: under union role
 * resolution a lower grant can never reduce what a higher one already
 * grants, so a UI that implies "uncheck to remove" would simply be lying.
 * Every grant is additive here, and the effective-capabilities preview
 * (design D10) is wired against the exact function that enforces access, so
 * what this screen shows is provably what saving would actually grant.
 */

type GrantLevel = 'project' | 'environment';

interface ActiveMember {
  membershipId: string;
  userId: number;
  username: string;
  orgRole: OrganizationRole;
}

interface GrantForm {
  level: GrantLevel;
  targetId: string;
  role: ProjectRole | EnvironmentRole;
}

export default function MembersPage() {
  const t = useTranslations('membersPage');
  const { success, error: showError } = useToast();
  const errorCopy = useErrorCopy();

  // Translated labels can only be read inside the component, unlike the raw
  // `value`s below (which are the backend's role enums and stay untranslated)
  // -- see the same reasoning on `TABS` in `dashboard-nav.tsx` and `OPERATORS`
  // in `flags/[id]/rules/page.tsx`. Render-only, like both of those, so no
  // memoization: neither array is read from a `useCallback`/`useEffect`/
  // `useMemo` dependency array anywhere in this file.
  const ORG_ROLE_OPTIONS: { value: OrganizationRole; label: string }[] = [
    { value: 'USER', label: t('orgRoleOptionUser') },
    { value: 'ADMIN', label: t('orgRoleOptionAdmin') },
  ];

  const GRANT_ROLE_OPTIONS: { value: ProjectRole; label: string }[] = [
    { value: 'VIEWER', label: t('grantRoleOptionViewer') },
    { value: 'OPERATOR', label: t('grantRoleOptionOperator') },
    { value: 'EDITOR', label: t('grantRoleOptionEditor') },
    { value: 'ADMIN', label: t('grantRoleOptionAdmin') },
  ];
  const {
    currentOrganization,
    projects,
    currentProject,
    isLoading: isTenantLoading,
  } = useTenant();

  const [orgMembers, setOrgMembers] = useState<OrganizationMembership[]>([]);
  const [isLoadingMembers, setIsLoadingMembers] = useState(true);

  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [projectGrants, setProjectGrants] = useState<ProjectMembership[]>([]);
  const [envGrants, setEnvGrants] = useState<EnvironmentMembership[]>([]);
  const [isLoadingGrants, setIsLoadingGrants] = useState(true);

  // Organization-wide (not just `currentProject`) grants, kept only to tell
  // apart a member who has never been granted anything from one whose access
  // lives in a different project of this same organization -- a person can
  // create a member and still see nobody flagged just because they happened
  // to be looking at project A while the grant landed on project B.
  const [orgProjectGrants, setOrgProjectGrants] = useState<ProjectMembership[]>(
    [],
  );
  const [orgEnvGrants, setOrgEnvGrants] = useState<EnvironmentMembership[]>([]);

  const [memberToRemove, setMemberToRemove] =
    useState<OrganizationMembership | null>(null);
  const [isRemovingMember, setIsRemovingMember] = useState(false);

  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [isLoadingInvitations, setIsLoadingInvitations] = useState(true);

  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [inviteRole, setInviteRole] = useState<OrganizationRole>('USER');
  const [isCreatingInvite, setIsCreatingInvite] = useState(false);
  // Holds the plaintext token only for the moment between creating it and
  // closing this dialog -- it is never retrievable again after that (the
  // backend never returns it from any read endpoint).
  const [createdInvite, setCreatedInvite] =
    useState<InvitationWithToken | null>(null);

  const [invitationToRevoke, setInvitationToRevoke] =
    useState<Invitation | null>(null);
  const [isRevokingInvitation, setIsRevokingInvitation] = useState(false);

  const [activeMember, setActiveMember] = useState<ActiveMember | null>(null);
  const [isGrantDialogOpen, setIsGrantDialogOpen] = useState(false);
  const [grantForm, setGrantForm] = useState<GrantForm>({
    level: 'project',
    targetId: '',
    role: 'VIEWER',
  });
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isSavingGrant, setIsSavingGrant] = useState(false);
  const [previewResult, setPreviewResult] = useState<
    EffectiveCapabilitiesPreviewEnvironment[] | null
  >(null);
  const [previewedSignature, setPreviewedSignature] = useState<string | null>(
    null,
  );

  const loadOrgMembers = useCallback(async () => {
    if (!currentOrganization) {
      setOrgMembers([]);
      setIsLoadingMembers(false);
      return;
    }
    setIsLoadingMembers(true);
    try {
      const response = await organizationMembershipsApi.list();
      // No `?organization=` filter exists on this viewset (task 8.3): it
      // scopes by every organization the caller can see, so narrow here.
      setOrgMembers(
        response.results.filter(
          (member) => member.organization === currentOrganization.id,
        ),
      );
    } catch {
      setOrgMembers([]);
    } finally {
      setIsLoadingMembers(false);
    }
  }, [currentOrganization]);

  useEffect(() => {
    loadOrgMembers();
  }, [loadOrgMembers]);

  const loadInvitations = useCallback(async () => {
    if (!currentOrganization) {
      setInvitations([]);
      setIsLoadingInvitations(false);
      return;
    }
    setIsLoadingInvitations(true);
    try {
      const response = await invitationsApi.list();
      // No `?organization=` filter exists on this viewset either -- narrow
      // client-side, same pattern as organization memberships above.
      setInvitations(
        response.results.filter(
          (invitation) => invitation.organization === currentOrganization.id,
        ),
      );
    } catch {
      setInvitations([]);
    } finally {
      setIsLoadingInvitations(false);
    }
  }, [currentOrganization]);

  useEffect(() => {
    loadInvitations();
  }, [loadInvitations]);

  const pendingInvitations = useMemo(
    () => invitations.filter((invitation) => invitation.status === 'pending'),
    [invitations],
  );

  const loadProjectGrants = useCallback(async () => {
    if (!currentProject) {
      setEnvironments([]);
      setProjectGrants([]);
      setEnvGrants([]);
      setIsLoadingGrants(false);
      return;
    }
    setIsLoadingGrants(true);
    try {
      const [
        environmentsRes,
        projectMembershipsRes,
        environmentMembershipsRes,
      ] = await Promise.all([
        environmentsApi.list({ project: currentProject.id }),
        projectMembershipsApi.list(),
        environmentMembershipsApi.list(),
      ]);
      const envIds = new Set(environmentsRes.results.map((env) => env.id));
      setEnvironments(environmentsRes.results);
      // Neither viewset takes a `?project=`/`?environment=` filter (task
      // 8.3), so narrow to the current project client-side.
      setProjectGrants(
        projectMembershipsRes.results.filter(
          (grant) => grant.project === currentProject.id,
        ),
      );
      setEnvGrants(
        environmentMembershipsRes.results.filter((grant) =>
          envIds.has(grant.environment),
        ),
      );
    } catch {
      setEnvironments([]);
      setProjectGrants([]);
      setEnvGrants([]);
    } finally {
      setIsLoadingGrants(false);
    }
  }, [currentProject]);

  useEffect(() => {
    loadProjectGrants();
  }, [loadProjectGrants]);

  const loadOrgWideGrants = useCallback(async () => {
    if (!currentOrganization || projects.length === 0) {
      setOrgProjectGrants([]);
      setOrgEnvGrants([]);
      return;
    }
    try {
      const projectIds = new Set(projects.map((project) => project.id));
      const [
        projectMembershipsRes,
        environmentsRes,
        environmentMembershipsRes,
      ] = await Promise.all([
        projectMembershipsApi.list(),
        environmentsApi.list(),
        environmentMembershipsApi.list(),
      ]);
      const orgEnvironmentIds = new Set(
        environmentsRes.results
          .filter((env) => projectIds.has(env.project))
          .map((env) => env.id),
      );
      setOrgProjectGrants(
        projectMembershipsRes.results.filter((grant) =>
          projectIds.has(grant.project),
        ),
      );
      setOrgEnvGrants(
        environmentMembershipsRes.results.filter((grant) =>
          orgEnvironmentIds.has(grant.environment),
        ),
      );
    } catch {
      setOrgProjectGrants([]);
      setOrgEnvGrants([]);
    }
  }, [currentOrganization, projects]);

  useEffect(() => {
    loadOrgWideGrants();
  }, [loadOrgWideGrants]);

  /**
   * "Has access" means "resolves to a non-empty capability set", not "holds
   * a grant row" -- the same distinction `resolve_capabilities`
   * (tenancy/capabilities.py) draws between rows and resolved capabilities.
   * An organization ADMIN's org-level role alone resolves to
   * `ALL_CAPABILITIES` (`_ORG_ADMIN_CAPS`): that is the entire org-level
   * catalogue, fixed at exactly two roles, so replicating it here is not a
   * second approximate resolution, it is the one place capability
   * membership could ever go besides the constant itself. An org ADMIN must
   * therefore never be badged, regardless of whether they hold any project
   * or environment grant row.
   */
  const membersWithoutAccess = useMemo(() => {
    const withAccess = new Set([
      ...orgProjectGrants.map((grant) => grant.user),
      ...orgEnvGrants.map((grant) => grant.user),
    ]);
    return new Set(
      orgMembers
        .filter(
          (member) => member.role !== 'ADMIN' && !withAccess.has(member.user),
        )
        .map((member) => member.id),
    );
  }, [orgMembers, orgProjectGrants, orgEnvGrants]);

  // The backend refuses to remove (or demote) the last ADMIN of an
  // organization (`last_admin_cannot_be_removed`). Offering the action
  // anyway would just teach people it fails, so it is never presented for
  // whichever ADMIN row is currently the only one left.
  const orgAdminCount = useMemo(
    () => orgMembers.filter((member) => member.role === 'ADMIN').length,
    [orgMembers],
  );

  const grantRows = useMemo(() => {
    const fromProjects = projectGrants.map((grant) => ({
      id: grant.id,
      user: grant.user,
      username: grant.username,
      level: 'Project' as const,
      targetId: grant.project,
      target: currentProject?.name ?? grant.project,
      role: grant.role as ProjectRole | EnvironmentRole,
    }));
    const fromEnvironments = envGrants.map((grant) => ({
      id: grant.id,
      user: grant.user,
      username: grant.username,
      level: 'Environment' as const,
      targetId: grant.environment,
      target:
        environments.find((env) => env.id === grant.environment)?.name ??
        grant.environment,
      role: grant.role as ProjectRole | EnvironmentRole,
    }));
    return [...fromProjects, ...fromEnvironments];
  }, [projectGrants, envGrants, environments, currentProject]);

  const currentSignature = useMemo(
    () =>
      JSON.stringify({
        member: activeMember?.userId,
        project: currentProject?.id,
        ...grantForm,
      }),
    [activeMember, currentProject, grantForm],
  );

  const openGrantDialog = useCallback(
    (member: OrganizationMembership, prefill?: GrantForm) => {
      setActiveMember({
        membershipId: member.id,
        userId: member.user,
        username: member.username,
        orgRole: member.role,
      });
      setGrantForm(
        prefill ?? {
          level: 'project',
          targetId: currentProject?.id ?? '',
          role: 'VIEWER',
        },
      );
      setPreviewResult(null);
      setPreviewedSignature(null);
      setIsGrantDialogOpen(true);
    },
    [currentProject],
  );

  /**
   * The grant already held by `activeMember` at the form's current
   * level/target, if any -- re-POSTing an existing (project, user) or
   * (environment, user) pair collides with the row's unique constraint
   * (`non_field_errors: ... must make a unique set`). Its presence switches
   * the confirm action from create to update.
   */
  const existingMembershipId = useMemo(() => {
    if (!activeMember) return null;
    if (grantForm.level === 'project') {
      return (
        projectGrants.find(
          (grant) =>
            grant.user === activeMember.userId &&
            grant.project === grantForm.targetId,
        )?.id ?? null
      );
    }
    return (
      envGrants.find(
        (grant) =>
          grant.user === activeMember.userId &&
          grant.environment === grantForm.targetId,
      )?.id ?? null
    );
  }, [activeMember, grantForm, projectGrants, envGrants]);

  const closeInviteDialog = () => {
    setIsInviteOpen(false);
    setCreatedInvite(null);
    setInviteRole('USER');
  };

  const handleCreateInvite = async () => {
    if (!currentOrganization) return;
    setIsCreatingInvite(true);
    try {
      const invitation = await invitationsApi.create({
        organization: currentOrganization.id,
        role: inviteRole,
      });
      // Swap the dialog into its reveal phase -- this is the one and only
      // time the plaintext token is ever visible.
      setCreatedInvite(invitation);
      loadInvitations();
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('createInviteErrorFallback'),
      );
    } finally {
      setIsCreatingInvite(false);
    }
  };

  const handleCopyInviteLink = async () => {
    if (!createdInvite) return;
    const link = createdInvite.link;
    try {
      await navigator.clipboard.writeText(link);
      success(t('inviteLinkCopiedToast'));
    } catch {
      showError(t('copyLinkErrorToast'));
    }
  };

  const handleRevokeInvitation = async () => {
    if (!invitationToRevoke) return;
    setIsRevokingInvitation(true);
    try {
      await invitationsApi.revoke(invitationToRevoke.id);
      success(t('revokeInvitationSuccessToast'));
      setInvitationToRevoke(null);
      loadInvitations();
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('revokeInvitationErrorFallback'),
      );
    } finally {
      setIsRevokingInvitation(false);
    }
  };

  const handlePreview = async () => {
    if (!activeMember || !currentOrganization || !currentProject) return;
    if (grantForm.level === 'environment' && !grantForm.targetId) return;
    setIsPreviewing(true);
    try {
      const payload =
        grantForm.level === 'project'
          ? {
              organization: currentOrganization.id,
              organization_role: activeMember.orgRole,
              project_roles: {
                [currentProject.id]: grantForm.role as ProjectRole,
              },
              // Duplicating the project role as the SAME-named environment
              // role for every environment in the project is always safe: a
              // project role's capability set is a strict superset of the
              // same-named environment role's, so this never overstates what
              // the project grant alone would give. It is also the only way
              // to see a per-environment result at all, because the preview
              // endpoint only returns environments named as keys in
              // `environment_roles`.
              environment_roles: Object.fromEntries(
                environments.map((env) => [
                  env.id,
                  grantForm.role as EnvironmentRole,
                ]),
              ),
            }
          : {
              organization: currentOrganization.id,
              organization_role: activeMember.orgRole,
              project_roles: {},
              environment_roles: {
                [grantForm.targetId]: grantForm.role as EnvironmentRole,
              },
            };
      const response = await effectiveCapabilitiesApi.preview(payload);
      setPreviewResult(response.environments);
      setPreviewedSignature(currentSignature);
    } catch (err) {
      showError(err instanceof Error ? err.message : t('previewErrorFallback'));
    } finally {
      setIsPreviewing(false);
    }
  };

  const handleConfirmGrant = async () => {
    if (
      !activeMember ||
      !currentProject ||
      previewedSignature !== currentSignature
    )
      return;
    setIsSavingGrant(true);
    try {
      // An existing grant is changed in place (PATCH), never re-created:
      // re-POSTing the same (project, user) or (environment, user) pair
      // collides with the row's unique constraint.
      if (grantForm.level === 'project') {
        if (existingMembershipId) {
          await projectMembershipsApi.updateRole(
            existingMembershipId,
            grantForm.role as ProjectRole,
          );
        } else {
          await projectMembershipsApi.create({
            project: currentProject.id,
            user: activeMember.userId,
            role: grantForm.role as ProjectRole,
          });
        }
      } else if (existingMembershipId) {
        await environmentMembershipsApi.updateRole(
          existingMembershipId,
          grantForm.role as EnvironmentRole,
        );
      } else {
        await environmentMembershipsApi.create({
          environment: grantForm.targetId,
          user: activeMember.userId,
          role: grantForm.role as EnvironmentRole,
        });
      }
      success(
        t('grantSuccessToast', {
          action: existingMembershipId ? 'updated' : 'granted',
          role: grantForm.role,
          username: activeMember.username,
        }),
      );
      setIsGrantDialogOpen(false);
      loadProjectGrants();
      loadOrgWideGrants();
    } catch (err) {
      showError(err instanceof Error ? err.message : t('grantErrorFallback'));
    } finally {
      setIsSavingGrant(false);
    }
  };

  const handleRevoke = async (row: {
    id: string;
    level: 'Project' | 'Environment';
    username: string;
  }) => {
    try {
      if (row.level === 'Project') {
        await projectMembershipsApi.remove(row.id);
      } else {
        await environmentMembershipsApi.remove(row.id);
      }
      success(
        t('revokeGrantSuccessToast', {
          level: row.level.toLowerCase(),
          username: row.username,
        }),
      );
      loadProjectGrants();
      loadOrgWideGrants();
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('revokeGrantErrorFallback'),
      );
    }
  };

  const handleRemoveMember = async () => {
    if (!memberToRemove) return;
    setIsRemovingMember(true);
    try {
      await organizationMembershipsApi.remove(memberToRemove.id);
      success(
        t('removeMemberSuccessToast', { username: memberToRemove.username }),
      );
      setMemberToRemove(null);
      // Removal cascades (#23): every project and environment grant this
      // person held in this organization is revoked with them, so the grants
      // table needs a refresh alongside the members list.
      loadOrgMembers();
      loadProjectGrants();
      loadOrgWideGrants();
    } catch (err) {
      // Through the shared copy table -- e.g. `last_admin_cannot_be_removed`
      // if this member became the last ADMIN in a race with another remover.
      // A code with no copy still reaches the user as itself.
      showError(
        err instanceof Error
          ? errorCopy(err.message)
          : t('removeMemberErrorFallback'),
      );
    } finally {
      setIsRemovingMember(false);
    }
  };

  if (isTenantLoading) {
    // The description interpolates `currentOrganization.name`, which is
    // still null at this point (tenant data has not arrived yet) -- so
    // unlike the title, it stays a skeleton rather than rendering for real.
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('pageTitle')}
          description={<Skeleton className="h-4 w-80" />}
        />
        <LoadingRegion className="space-y-6">
          <Skeleton className="h-20 w-full" />
          <Card>
            <CardContent>
              <DataTableSkeleton columns={3} />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <DataTableSkeleton columns={4} />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <DataTableSkeleton columns={5} />
            </CardContent>
          </Card>
        </LoadingRegion>
      </div>
    );
  }

  if (!currentOrganization) {
    return (
      <EmptyState
        icon={UserPlus}
        title={t('noOrganizationTitle')}
        description={t('noOrganizationDescription')}
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('pageTitle')}
        description={t('pageDescription', {
          organizationName: currentOrganization.name,
        })}
        action={
          <Dialog
            open={isInviteOpen}
            onOpenChange={(open) => {
              if (open) {
                setIsInviteOpen(true);
              } else {
                closeInviteDialog();
              }
            }}
          >
            <DialogTrigger render={<Button variant="outline" />}>
              <Mail className="mr-2 h-4 w-4" />
              {t('inviteByLinkButton')}
            </DialogTrigger>
            <DialogContent>
              {createdInvite ? (
                <>
                  <DialogHeader>
                    <DialogTitle>{t('inviteLinkCreatedTitle')}</DialogTitle>
                    <DialogDescription>
                      {t('inviteLinkCreatedDescription')}
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-2">
                    <Label htmlFor="invite-link">
                      {t('singleUseLinkLabel')}
                    </Label>
                    <div className="flex gap-2">
                      <Input
                        id="invite-link"
                        readOnly
                        value={createdInvite.link}
                        onFocus={(e) => e.currentTarget.select()}
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={handleCopyInviteLink}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      {t.rich('inviteRoleLine', {
                        role: () => (
                          <Badge
                            variant={
                              createdInvite.role === 'ADMIN'
                                ? 'warning'
                                : 'muted'
                            }
                          >
                            {createdInvite.role}
                          </Badge>
                        ),
                        expiresAt: formatRelativeTime(createdInvite.expires_at),
                      })}
                    </p>
                  </div>
                  <DialogFooter>
                    <Button onClick={closeInviteDialog}>
                      {t('doneButton')}
                    </Button>
                  </DialogFooter>
                </>
              ) : (
                <>
                  <DialogHeader>
                    <DialogTitle>{t('inviteByLinkDialogTitle')}</DialogTitle>
                    <DialogDescription>
                      {t('inviteByLinkDialogDescription')}
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-2">
                    <Label htmlFor="invite-role">
                      {t('organizationRoleLabel')}
                    </Label>
                    <select
                      id="invite-role"
                      className="w-full rounded-md border border-border bg-muted p-2 text-foreground"
                      value={inviteRole}
                      onChange={(e) =>
                        setInviteRole(e.target.value as OrganizationRole)
                      }
                    >
                      {ORG_ROLE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={closeInviteDialog}>
                      {t('cancelButton')}
                    </Button>
                    <Button
                      onClick={handleCreateInvite}
                      disabled={isCreatingInvite}
                    >
                      {isCreatingInvite ? (
                        <Spinner size="sm" className="mr-2" />
                      ) : null}
                      {t('createLinkButton')}
                    </Button>
                  </DialogFooter>
                </>
              )}
            </DialogContent>
          </Dialog>
        }
      />

      <Card className="border-info/25 bg-info/5">
        <CardContent className="flex items-start gap-2 py-4 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0 text-info" />
          <p>
            {t.rich('accessInfoCallout', {
              strong: (chunks) => <strong>{chunks}</strong>,
            })}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('orgMembersCardTitle')}</CardTitle>
          <CardDescription>
            {t('orgMembersCardDescription', {
              count: orgMembers.length,
              organizationName: currentOrganization.name,
            })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoadingMembers ? (
            <LoadingRegion label={t('orgMembersLoadingLabel')}>
              <DataTableSkeleton columns={3} />
            </LoadingRegion>
          ) : orgMembers.length === 0 ? (
            <EmptyState
              icon={UserPlus}
              title={t('noMembersTitle')}
              description={t('noMembersDescription')}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground">
                    {t('usernameHeader')}
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    {t('organizationRoleHeader')}
                  </TableHead>
                  <TableHead className="w-[260px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {orgMembers.map((member) => (
                  <TableRow key={member.id} className="border-border">
                    <TableCell className="font-medium text-foreground">
                      <div className="flex items-center gap-2">
                        {member.username}
                        {membersWithoutAccess.has(member.id) ? (
                          <Badge variant="warning">
                            <Lock className="size-3" />
                            {t('noProjectAccessBadge')}
                          </Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={member.role === 'ADMIN' ? 'warning' : 'muted'}
                      >
                        {member.role === 'ADMIN' ? (
                          <ShieldAlert className="size-3" />
                        ) : null}
                        {member.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1.5">
                        {/*
                         * Not offered for an organization ADMIN, who already
                         * holds the whole capability catalogue. Under union
                         * resolution a project or environment grant can only
                         * add, so granting one here changes nothing -- while
                         * implying it narrows them to that project, which is
                         * the same lie this screen refuses to tell with a
                         * checkbox grid (see the note at the top of the file).
                         * The control that actually limits an ADMIN is the
                         * organization role itself: demote them to USER.
                         * Existing grant rows keep their edit and remove
                         * actions; deleting a stale one is real cleanup.
                         */}
                        {member.role === 'ADMIN' ? null : (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={!currentProject}
                            onClick={() => openGrantDialog(member)}
                          >
                            <Plus className="mr-1 h-3.5 w-3.5" />
                            {t('grantRoleButton')}
                          </Button>
                        )}
                        {member.role === 'ADMIN' &&
                        orgAdminCount <= 1 ? null : (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => setMemberToRemove(member)}
                          >
                            <UserMinus className="mr-1 h-3.5 w-3.5" />
                            {t('removeMemberButton')}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('pendingInvitationsCardTitle')}</CardTitle>
          <CardDescription>
            {t('pendingInvitationsCardDescription')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoadingInvitations ? (
            <LoadingRegion label={t('pendingInvitationsLoadingLabel')}>
              <DataTableSkeleton columns={4} />
            </LoadingRegion>
          ) : pendingInvitations.length === 0 ? (
            <EmptyState
              icon={Mail}
              title={t('noPendingInvitationsTitle')}
              description={t('noPendingInvitationsDescription')}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground">
                    {t('roleHeader')}
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    {t('invitedByHeader')}
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    {t('expiresHeader')}
                  </TableHead>
                  <TableHead className="w-[120px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {pendingInvitations.map((invitation) => (
                  <TableRow key={invitation.id} className="border-border">
                    <TableCell>
                      <Badge
                        variant={
                          invitation.role === 'ADMIN' ? 'warning' : 'muted'
                        }
                      >
                        {invitation.role}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {invitation.created_by_username ??
                        t('unknownInviterFallback')}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatRelativeTime(invitation.expires_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end">
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setInvitationToRevoke(invitation)}
                        >
                          <Ban className="mr-1 h-3.5 w-3.5" />
                          {t('revokeButton')}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            {t('grantsCardTitle', {
              hasProject: currentProject ? 'yes' : 'no',
              projectName: currentProject?.name ?? '',
            })}
          </CardTitle>
          <CardDescription>
            {t('grantsCardDescription', {
              hasProject: currentProject ? 'yes' : 'no',
            })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!currentProject ? (
            <EmptyState
              icon={UserPlus}
              title={t('noProjectSelectedTitle')}
              description={t('noProjectSelectedDescription')}
            />
          ) : isLoadingGrants ? (
            <LoadingRegion label={t('grantsLoadingLabel')}>
              <DataTableSkeleton columns={5} />
            </LoadingRegion>
          ) : grantRows.length === 0 ? (
            <EmptyState
              icon={UserPlus}
              title={t('noGrantsTitle')}
              description={t('noGrantsDescription')}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground">
                    {t('userHeader')}
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    {t('levelHeader')}
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    {t('targetHeader')}
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    {t('roleHeader')}
                  </TableHead>
                  <TableHead className="w-[160px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {grantRows.map((grant) => (
                  <TableRow key={grant.id} className="border-border">
                    <TableCell className="text-foreground">
                      {grant.username}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {grant.level === 'Project'
                        ? t('levelCellProject')
                        : t('levelCellEnvironment')}
                    </TableCell>
                    <TableCell className="text-foreground">
                      {grant.target}
                    </TableCell>
                    <TableCell>
                      <Badge variant="muted">{grant.role}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            const member = orgMembers.find(
                              (candidate) => candidate.user === grant.user,
                            );
                            if (!member) return;
                            openGrantDialog(member, {
                              level:
                                grant.level === 'Project'
                                  ? 'project'
                                  : 'environment',
                              targetId: grant.targetId,
                              role: grant.role,
                            });
                          }}
                        >
                          {t('changeRoleButton')}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => handleRevoke(grant)}
                        >
                          {t('revokeButton')}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={isGrantDialogOpen} onOpenChange={setIsGrantDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('grantDialogTitle', {
                action: existingMembershipId ? 'change' : 'grant',
                username: activeMember?.username ?? t('thisMemberFallback'),
              })}
            </DialogTitle>
            <DialogDescription>
              {t('grantDialogDescription', {
                context: existingMembershipId ? 'existing' : 'new',
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="grant-level">{t('levelLabel')}</Label>
              <select
                id="grant-level"
                className="w-full rounded-md border border-border bg-muted p-2 text-foreground"
                value={grantForm.level}
                onChange={(e) => {
                  const level = e.target.value as GrantLevel;
                  setGrantForm({
                    level,
                    targetId:
                      level === 'project' ? (currentProject?.id ?? '') : '',
                    role: 'VIEWER',
                  });
                  setPreviewResult(null);
                  setPreviewedSignature(null);
                }}
              >
                <option value="project">
                  {t('grantLevelSelectProjectOption', {
                    projectName:
                      currentProject?.name ?? t('currentProjectFallback'),
                  })}
                </option>
                <option value="environment">
                  {t('grantLevelSelectEnvironmentOption')}
                </option>
              </select>
            </div>

            {grantForm.level === 'environment' ? (
              <div className="space-y-2">
                <Label htmlFor="grant-target">
                  {t('grantTargetEnvironmentLabel')}
                </Label>
                <select
                  id="grant-target"
                  className="w-full rounded-md border border-border bg-muted p-2 text-foreground"
                  value={grantForm.targetId}
                  onChange={(e) => {
                    setGrantForm({ ...grantForm, targetId: e.target.value });
                    setPreviewResult(null);
                    setPreviewedSignature(null);
                  }}
                >
                  <option value="">{t('selectEnvironmentOption')}</option>
                  {environments.map((env) => (
                    <option key={env.id} value={env.id}>
                      {env.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}

            <div className="space-y-2">
              <Label htmlFor="grant-role">{t('roleLabel')}</Label>
              <select
                id="grant-role"
                className="w-full rounded-md border border-border bg-muted p-2 text-foreground"
                value={grantForm.role}
                onChange={(e) => {
                  setGrantForm({
                    ...grantForm,
                    role: e.target.value as ProjectRole,
                  });
                  setPreviewResult(null);
                  setPreviewedSignature(null);
                }}
              >
                {GRANT_ROLE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2 rounded-md border border-border bg-card p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-foreground">
                  {t('previewSectionTitle')}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    isPreviewing ||
                    (grantForm.level === 'environment' && !grantForm.targetId)
                  }
                  onClick={handlePreview}
                >
                  {isPreviewing ? <Spinner size="sm" className="mr-1" /> : null}
                  {t('previewButton')}
                </Button>
              </div>
              {previewResult === null ? (
                <p className="text-xs text-muted-foreground">
                  {t('previewHintBeforeRun')}
                </p>
              ) : previewResult.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  {t('previewNoEnvironments')}
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {previewResult.map((env) => (
                    <li key={env.id} className="text-xs">
                      <span className="font-mono text-foreground">
                        {env.key}
                      </span>
                      {': '}
                      {env.capabilities.length === 0 ? (
                        <span className="text-muted-foreground">
                          {t('previewGainsNothing')}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">
                          {env.capabilities.join(', ')}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsGrantDialogOpen(false)}
            >
              {t('cancelButton')}
            </Button>
            <Button
              onClick={handleConfirmGrant}
              disabled={
                isSavingGrant ||
                previewedSignature !== currentSignature ||
                (grantForm.level === 'environment' && !grantForm.targetId)
              }
            >
              {isSavingGrant ? <Spinner size="sm" className="mr-2" /> : null}
              {t('confirmGrantButton', {
                hasExistingGrant: existingMembershipId ? 'yes' : 'no',
              })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={memberToRemove !== null}
        onOpenChange={(open) => {
          if (!open) setMemberToRemove(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('removeMemberDialogTitle', {
                username: memberToRemove?.username ?? '',
              })}
            </DialogTitle>
            <DialogDescription>
              {t('removeMemberDialogDescription', {
                organizationName: currentOrganization.name,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setMemberToRemove(null)}
              disabled={isRemovingMember}
            >
              {t('cancelButton')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleRemoveMember}
              disabled={isRemovingMember}
            >
              {isRemovingMember ? <Spinner size="sm" className="mr-2" /> : null}
              {t('removeMemberConfirmButton')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={invitationToRevoke !== null}
        onOpenChange={(open) => {
          if (!open) setInvitationToRevoke(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('revokeInvitationDialogTitle')}</DialogTitle>
            <DialogDescription>
              {t('revokeInvitationDialogDescription', {
                organizationName: currentOrganization.name,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setInvitationToRevoke(null)}
              disabled={isRevokingInvitation}
            >
              {t('cancelButton')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleRevokeInvitation}
              disabled={isRevokingInvitation}
            >
              {isRevokingInvitation ? (
                <Spinner size="sm" className="mr-2" />
              ) : null}
              {t('revokeInvitationConfirmButton')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
