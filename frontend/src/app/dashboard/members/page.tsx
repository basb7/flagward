'use client';

import { Info, Plus, ShieldAlert, UserPlus } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
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
import { PageHeader } from '@/components/ui/page-header';
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
  type OrganizationMembership,
  type OrganizationRole,
  organizationMembersApi,
  organizationMembershipsApi,
  type ProjectMembership,
  type ProjectRole,
  projectMembershipsApi,
} from '@/lib/api';
import { useTenant } from '@/lib/tenant-context';
import { useToast } from '@/lib/toast-context';

/**
 * The Members screen never renders a checkbox grid: under union role
 * resolution a lower grant can never reduce what a higher one already
 * grants, so a UI that implies "uncheck to remove" would simply be lying.
 * Every grant is additive here, and the effective-capabilities preview
 * (design D10) is wired against the exact function that enforces access, so
 * what this screen shows is provably what saving would actually grant.
 */

const ORG_ROLE_OPTIONS: { value: OrganizationRole; label: string }[] = [
  { value: 'USER', label: 'User — org.view only, nothing about projects' },
  { value: 'ADMIN', label: 'Admin — full key to the account' },
];

const GRANT_ROLE_OPTIONS: { value: ProjectRole; label: string }[] = [
  { value: 'VIEWER', label: 'Viewer' },
  { value: 'OPERATOR', label: 'Operator' },
  { value: 'EDITOR', label: 'Editor' },
  { value: 'ADMIN', label: 'Admin' },
];

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
  const { success, error: showError } = useToast();
  const {
    currentOrganization,
    currentProject,
    isLoading: isTenantLoading,
  } = useTenant();

  const [orgMembers, setOrgMembers] = useState<OrganizationMembership[]>([]);
  const [isLoadingMembers, setIsLoadingMembers] = useState(true);

  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [projectGrants, setProjectGrants] = useState<ProjectMembership[]>([]);
  const [envGrants, setEnvGrants] = useState<EnvironmentMembership[]>([]);
  const [isLoadingGrants, setIsLoadingGrants] = useState(true);

  const [isAddMemberOpen, setIsAddMemberOpen] = useState(false);
  const [isSavingMember, setIsSavingMember] = useState(false);
  const [newMember, setNewMember] = useState({
    username: '',
    email: '',
    password: '',
    role: 'USER' as OrganizationRole,
  });

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

  const grantRows = useMemo(() => {
    const fromProjects = projectGrants.map((grant) => ({
      id: grant.id,
      username: grant.username,
      level: 'Project' as const,
      target: currentProject?.name ?? grant.project,
      role: grant.role as ProjectRole | EnvironmentRole,
    }));
    const fromEnvironments = envGrants.map((grant) => ({
      id: grant.id,
      username: grant.username,
      level: 'Environment' as const,
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
    (member: OrganizationMembership) => {
      setActiveMember({
        membershipId: member.id,
        userId: member.user,
        username: member.username,
        orgRole: member.role,
      });
      setGrantForm({
        level: 'project',
        targetId: currentProject?.id ?? '',
        role: 'VIEWER',
      });
      setPreviewResult(null);
      setPreviewedSignature(null);
      setIsGrantDialogOpen(true);
    },
    [currentProject],
  );

  const handleAddMember = async () => {
    if (!currentOrganization) return;
    setIsSavingMember(true);
    try {
      await organizationMembersApi.create(currentOrganization.id, newMember);
      setIsAddMemberOpen(false);
      setNewMember({ username: '', email: '', password: '', role: 'USER' });
      success(`${newMember.username} added to the organization`);
      loadOrgMembers();
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to add member');
    } finally {
      setIsSavingMember(false);
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
      showError(err instanceof Error ? err.message : 'Failed to preview');
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
      if (grantForm.level === 'project') {
        await projectMembershipsApi.create({
          project: currentProject.id,
          user: activeMember.userId,
          role: grantForm.role as ProjectRole,
        });
      } else {
        await environmentMembershipsApi.create({
          environment: grantForm.targetId,
          user: activeMember.userId,
          role: grantForm.role as EnvironmentRole,
        });
      }
      success(`Granted ${grantForm.role} to ${activeMember.username}`);
      setIsGrantDialogOpen(false);
      loadProjectGrants();
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to grant role');
    } finally {
      setIsSavingGrant(false);
    }
  };

  if (isTenantLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!currentOrganization) {
    return (
      <EmptyState
        icon={UserPlus}
        title="No organization"
        description="No organization is visible for your account yet."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Members"
        description={`Manage who has access to ${currentOrganization.name} and what they can do.`}
        action={
          <Dialog open={isAddMemberOpen} onOpenChange={setIsAddMemberOpen}>
            <DialogTrigger render={<Button />}>
              <UserPlus className="mr-2 h-4 w-4" />
              Add member
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add a member</DialogTitle>
                <DialogDescription>
                  Creates a new account and attaches it to this organization.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="member-username">Username</Label>
                  <Input
                    id="member-username"
                    value={newMember.username}
                    onChange={(e) =>
                      setNewMember({ ...newMember, username: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="member-email">Email (optional)</Label>
                  <Input
                    id="member-email"
                    type="email"
                    value={newMember.email}
                    onChange={(e) =>
                      setNewMember({ ...newMember, email: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="member-password">Password</Label>
                  <Input
                    id="member-password"
                    type="password"
                    value={newMember.password}
                    onChange={(e) =>
                      setNewMember({ ...newMember, password: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="member-role">Organization role</Label>
                  <select
                    id="member-role"
                    className="w-full rounded-md border border-border bg-muted p-2 text-foreground"
                    value={newMember.role}
                    onChange={(e) =>
                      setNewMember({
                        ...newMember,
                        role: e.target.value as OrganizationRole,
                      })
                    }
                  >
                    {ORG_ROLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  {newMember.role === 'ADMIN' ? (
                    <p className="flex items-start gap-1.5 text-xs text-warning">
                      <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
                      Organization Admin holds `org.delete` — it cascades to
                      every project, environment, flag, rule and override in
                      this organization.
                    </p>
                  ) : null}
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setIsAddMemberOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleAddMember}
                  disabled={
                    isSavingMember ||
                    !newMember.username ||
                    newMember.password.length < 8
                  }
                >
                  {isSavingMember ? (
                    <Spinner size="sm" className="mr-2" />
                  ) : null}
                  Add member
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <Card className="border-info/25 bg-info/5">
        <CardContent className="flex items-start gap-2 py-4 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0 text-info" />
          <p>
            Roles at each level only ever <strong>add</strong> capabilities — a
            project or environment grant can never take away what a higher level
            already gives. There is no "remove access" toggle here on purpose:
            to reduce what someone can do, narrow the grant at the level it came
            from, not carve out an exception underneath a wider one.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Organization members</CardTitle>
          <CardDescription>
            {orgMembers.length} member(s) of {currentOrganization.name}. Grant a
            project or environment role to give access beyond {`org.view`}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoadingMembers ? (
            <div className="flex justify-center py-8">
              <Spinner size="lg" />
            </div>
          ) : orgMembers.length === 0 ? (
            <EmptyState
              icon={UserPlus}
              title="No members yet"
              description="Add a member to start granting project and environment roles."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground">
                    Username
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    Organization role
                  </TableHead>
                  <TableHead className="w-[140px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {orgMembers.map((member) => (
                  <TableRow key={member.id} className="border-border">
                    <TableCell className="font-medium text-foreground">
                      {member.username}
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
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={!currentProject}
                        onClick={() => openGrantDialog(member)}
                      >
                        <Plus className="mr-1 h-3.5 w-3.5" />
                        Grant role
                      </Button>
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
            {currentProject
              ? `Grants on ${currentProject.name}`
              : 'Project and environment grants'}
          </CardTitle>
          <CardDescription>
            {currentProject
              ? 'Project and environment roles held on this project and its environments.'
              : 'Select a project from the switcher above to see its grants.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!currentProject ? (
            <EmptyState
              icon={UserPlus}
              title="No project selected"
              description="Choose a project to view and grant its roles."
            />
          ) : isLoadingGrants ? (
            <div className="flex justify-center py-8">
              <Spinner size="lg" />
            </div>
          ) : grantRows.length === 0 ? (
            <EmptyState
              icon={UserPlus}
              title="No grants yet"
              description="Grant a project or environment role from the members table above."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground">User</TableHead>
                  <TableHead className="text-muted-foreground">Level</TableHead>
                  <TableHead className="text-muted-foreground">
                    Target
                  </TableHead>
                  <TableHead className="text-muted-foreground">Role</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {grantRows.map((grant) => (
                  <TableRow key={grant.id} className="border-border">
                    <TableCell className="text-foreground">
                      {grant.username}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {grant.level}
                    </TableCell>
                    <TableCell className="text-foreground">
                      {grant.target}
                    </TableCell>
                    <TableCell>
                      <Badge variant="muted">{grant.role}</Badge>
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
              Grant a role to {activeMember?.username ?? 'this member'}
            </DialogTitle>
            <DialogDescription>
              This adds a role — it can never remove what a higher level already
              grants. Preview the resolved capabilities before confirming.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="grant-level">Level</Label>
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
                  Project ({currentProject?.name ?? 'current project'})
                </option>
                <option value="environment">Environment</option>
              </select>
            </div>

            {grantForm.level === 'environment' ? (
              <div className="space-y-2">
                <Label htmlFor="grant-target">Environment</Label>
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
                  <option value="">Select environment</option>
                  {environments.map((env) => (
                    <option key={env.id} value={env.id}>
                      {env.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}

            <div className="space-y-2">
              <Label htmlFor="grant-role">Role</Label>
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
                  Effective capabilities preview
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
                  Preview
                </Button>
              </div>
              {previewResult === null ? (
                <p className="text-xs text-muted-foreground">
                  Run the preview to see exactly what this grant would give, per
                  environment, before saving it.
                </p>
              ) : previewResult.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No environments to show for this grant.
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
                          gains nothing new
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
              Cancel
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
              Confirm grant
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
