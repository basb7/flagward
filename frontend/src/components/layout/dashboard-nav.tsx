'use client';

import {
  Activity,
  Flag,
  Layers,
  LayoutGrid,
  LogOut,
  Pencil,
  Plus,
  Trash2,
  User,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { CreateOrganizationDialog } from '@/components/dashboard/create-organization-dialog';
import { CreateProjectDialog } from '@/components/dashboard/create-project-dialog';
import {
  DeleteResourceDialog,
  type ImpactField,
} from '@/components/dashboard/delete-resource-dialog';
import { RenameResourceDialog } from '@/components/dashboard/rename-resource-dialog';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  type OrganizationDeletionImpact,
  type ProjectDeletionImpact,
  tenancyApi,
} from '@/lib/api';
import { hasOrgCapability, useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { cn } from '@/lib/utils';

const ORGANIZATION_IMPACT_FIELDS: ImpactField<OrganizationDeletionImpact>[] = [
  { key: 'projects', singular: 'project' },
  { key: 'environments', singular: 'environment' },
  { key: 'flags', singular: 'flag' },
  { key: 'strategy_rules', singular: 'strategy rule' },
  { key: 'conditions', singular: 'condition' },
  { key: 'overrides', singular: 'override' },
  { key: 'evaluation_logs', singular: 'evaluation log' },
  { key: 'sdk_registrations', singular: 'SDK registration' },
  { key: 'organization_memberships', singular: 'organization membership' },
  { key: 'project_memberships', singular: 'project membership' },
  { key: 'environment_memberships', singular: 'environment membership' },
  { key: 'invitations', singular: 'invitation' },
];

const PROJECT_IMPACT_FIELDS: ImpactField<ProjectDeletionImpact>[] = [
  { key: 'environments', singular: 'environment' },
  { key: 'flags', singular: 'flag' },
  { key: 'strategy_rules', singular: 'strategy rule' },
  { key: 'conditions', singular: 'condition' },
  { key: 'overrides', singular: 'override' },
  { key: 'evaluation_logs', singular: 'evaluation log' },
  { key: 'sdk_registrations', singular: 'SDK registration' },
  { key: 'project_memberships', singular: 'project membership' },
  { key: 'environment_memberships', singular: 'environment membership' },
];

const TABS = [
  { href: '/dashboard', label: 'Overview', icon: LayoutGrid, exact: true },
  { href: '/dashboard/flags', label: 'Flags', icon: Flag },
  { href: '/dashboard/environments', label: 'Environments', icon: Layers },
  { href: '/dashboard/monitoring', label: 'Monitoring', icon: Activity },
  { href: '/dashboard/members', label: 'Members', icon: Users },
] as const;

export function DashboardNav() {
  const { user, logout } = useAuth();
  const {
    organizations,
    projects,
    currentProject,
    currentOrganization,
    setCurrentOrganization,
    setCurrentProject,
    refresh,
  } = useTenant();
  const pathname = usePathname();

  const isActive = (tab: (typeof TABS)[number]) =>
    'exact' in tab && tab.exact
      ? pathname === tab.href
      : pathname.startsWith(tab.href);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between gap-4">
          <Link href="/dashboard" className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-md bg-foreground text-background">
              <Flag className="size-3.5" />
            </span>
            <span className="font-heading text-sm font-semibold tracking-tight">
              Flagward
            </span>
          </Link>

          <div className="flex items-center gap-2">
            {organizations.length > 1 ? (
              <select
                aria-label="Organization"
                className="h-8 rounded-lg border border-border bg-card px-2 text-sm text-foreground"
                value={currentOrganization?.id ?? ''}
                onChange={(event) => {
                  const organization =
                    organizations.find(
                      (item) => item.id === event.target.value,
                    ) ?? null;
                  setCurrentOrganization(organization);
                }}
              >
                {organizations.map((organization) => (
                  <option key={organization.id} value={organization.id}>
                    {organization.name}
                  </option>
                ))}
              </select>
            ) : currentOrganization ? (
              <span
                role="status"
                aria-label="Organization"
                className="flex h-8 items-center rounded-lg border border-border bg-card px-2 text-sm text-foreground"
              >
                {currentOrganization.name}
              </span>
            ) : null}

            <CreateOrganizationDialog
              triggerButton={
                <Button
                  variant="ghost"
                  size="sm"
                  title="Create a new organization"
                  className="gap-1.5 text-muted-foreground hover:text-foreground"
                />
              }
              triggerContent={
                <>
                  <Plus className="size-4" />
                  <span className="sr-only sm:not-sr-only">
                    New organization
                  </span>
                </>
              }
              onCreated={async (organization) => {
                await refresh();
                setCurrentOrganization(organization);
              }}
            />

            {currentOrganization &&
            hasOrgCapability(user, currentOrganization.id, 'org.manage') ? (
              <RenameResourceDialog
                title="Rename organization"
                description="This name appears everywhere the organization is shown."
                toastMessage="Organization renamed"
                fields={[{ key: 'name', label: 'Name' }]}
                initialValues={{ name: currentOrganization.name }}
                onSave={async (values) => {
                  await tenancyApi.renameOrganization(currentOrganization.id, {
                    name: values.name,
                  });
                }}
                onSaved={refresh}
                triggerButton={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground hover:text-foreground"
                  />
                }
                triggerContent={
                  <>
                    <Pencil className="size-4" />
                    <span className="sr-only">Rename organization</span>
                  </>
                }
              />
            ) : null}

            {currentOrganization &&
            hasOrgCapability(user, currentOrganization.id, 'org.delete') ? (
              <DeleteResourceDialog<OrganizationDeletionImpact>
                resourceLabel="organization"
                resourceName={currentOrganization.name}
                fetchImpact={() =>
                  tenancyApi.organizationDeletionImpact(currentOrganization.id)
                }
                impactFields={ORGANIZATION_IMPACT_FIELDS}
                blockedWhen={(impact) =>
                  impact.other_members > 0
                    ? `This organization has ${impact.other_members} other member(s); remove them first before deleting it.`
                    : null
                }
                onDelete={(confirmName) =>
                  tenancyApi.deleteOrganization(
                    currentOrganization.id,
                    confirmName,
                  )
                }
                onDeleted={refresh}
                triggerButton={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground hover:text-destructive"
                  />
                }
                triggerContent={
                  <>
                    <Trash2 className="size-4" />
                    <span className="sr-only">Delete organization</span>
                  </>
                }
              />
            ) : null}

            <span aria-hidden="true" className="h-5 w-px bg-border" />

            {projects.length > 0 ? (
              <select
                aria-label="Project"
                className="h-8 rounded-lg border border-border bg-card px-2 text-sm text-foreground"
                value={currentProject?.id ?? ''}
                onChange={(event) => {
                  const project =
                    projects.find((item) => item.id === event.target.value) ??
                    null;
                  setCurrentProject(project);
                }}
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            ) : null}

            {currentOrganization ? (
              <CreateProjectDialog
                organizationId={currentOrganization.id}
                triggerButton={
                  <Button
                    variant="ghost"
                    size="sm"
                    title="Create a new project"
                    className="gap-1.5 text-muted-foreground hover:text-foreground"
                  />
                }
                triggerContent={
                  <>
                    <Plus className="size-4" />
                    <span className="sr-only sm:not-sr-only">New project</span>
                  </>
                }
                onCreated={(project) => {
                  refresh();
                  setCurrentProject(project);
                }}
              />
            ) : null}

            {currentProject ? (
              <RenameResourceDialog
                title="Rename project"
                description="The name and key both appear across the dashboard and API."
                toastMessage="Project renamed"
                fields={[
                  { key: 'name', label: 'Name' },
                  { key: 'key', label: 'Key' },
                ]}
                initialValues={{
                  name: currentProject.name,
                  key: currentProject.key,
                }}
                onSave={async (values) => {
                  await tenancyApi.renameProject(currentProject.id, values);
                }}
                onSaved={refresh}
                triggerButton={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground hover:text-foreground"
                  />
                }
                triggerContent={
                  <>
                    <Pencil className="size-4" />
                    <span className="sr-only">Rename project</span>
                  </>
                }
              />
            ) : null}

            {currentProject ? (
              <DeleteResourceDialog<ProjectDeletionImpact>
                resourceLabel="project"
                resourceName={currentProject.name}
                fetchImpact={() =>
                  tenancyApi.projectDeletionImpact(currentProject.id)
                }
                impactFields={PROJECT_IMPACT_FIELDS}
                onDelete={(confirmName) =>
                  tenancyApi.deleteProject(currentProject.id, confirmName)
                }
                onDeleted={refresh}
                triggerButton={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground hover:text-destructive"
                  />
                }
                triggerContent={
                  <>
                    <Trash2 className="size-4" />
                    <span className="sr-only">Delete project</span>
                  </>
                }
              />
            ) : null}

            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-2 text-muted-foreground hover:text-foreground"
                  />
                }
              >
                <User className="size-4" />
                <span className="max-w-32 truncate">{user?.username}</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={logout} className="text-destructive">
                  <LogOut className="mr-2 size-4" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        <nav
          aria-label="Dashboard sections"
          className="-mb-px flex gap-1 overflow-x-auto"
        >
          {TABS.map((tab) => {
            const active = isActive(tab);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-1.5 border-b-2 px-3 pb-2.5 text-sm whitespace-nowrap transition-colors',
                  active
                    ? 'border-foreground text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                <tab.icon className="size-4" />
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
