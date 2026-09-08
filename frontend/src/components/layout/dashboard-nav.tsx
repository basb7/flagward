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
import { useTranslations } from 'next-intl';
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
import { LanguageSwitcher } from '@/components/ui/language-switcher';
import { changeLocaleAction } from '@/i18n/actions';
import {
  type OrganizationDeletionImpact,
  type ProjectDeletionImpact,
  tenancyApi,
} from '@/lib/api';
import { hasOrgCapability, useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { cn } from '@/lib/utils';

const TAB_HREFS = [
  { href: '/dashboard', icon: LayoutGrid, exact: true },
  { href: '/dashboard/flags', icon: Flag },
  { href: '/dashboard/environments', icon: Layers },
  { href: '/dashboard/monitoring', icon: Activity },
  { href: '/dashboard/members', icon: Users },
] as const;

export function DashboardNav() {
  const t = useTranslations('dashboardNav');
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

  // Translated labels can only be read inside the component, unlike the
  // hrefs/icons in TAB_HREFS above -- so the tab list itself is built here,
  // per render, rather than once at module scope.
  const TABS = [
    { ...TAB_HREFS[0], label: t('tabOverview') },
    { ...TAB_HREFS[1], label: t('tabFlags') },
    { ...TAB_HREFS[2], label: t('tabEnvironments') },
    { ...TAB_HREFS[3], label: t('tabMonitoring') },
    { ...TAB_HREFS[4], label: t('tabMembers') },
  ] as const;

  // Same reasoning as TABS: each field's `label` calls an ICU plural message,
  // which needs `t` from this render, so these arrays live in the component
  // body instead of module scope.
  const ORGANIZATION_IMPACT_FIELDS: ImpactField<OrganizationDeletionImpact>[] =
    [
      {
        key: 'projects',
        label: (count) => t('impactFields.projects', { count }),
      },
      {
        key: 'environments',
        label: (count) => t('impactFields.environments', { count }),
      },
      { key: 'flags', label: (count) => t('impactFields.flags', { count }) },
      {
        key: 'strategy_rules',
        label: (count) => t('impactFields.strategyRules', { count }),
      },
      {
        key: 'conditions',
        label: (count) => t('impactFields.conditions', { count }),
      },
      {
        key: 'overrides',
        label: (count) => t('impactFields.overrides', { count }),
      },
      {
        key: 'evaluation_logs',
        label: (count) => t('impactFields.evaluationLogs', { count }),
      },
      {
        key: 'sdk_registrations',
        label: (count) => t('impactFields.sdkRegistrations', { count }),
      },
      {
        key: 'organization_memberships',
        label: (count) => t('impactFields.organizationMemberships', { count }),
      },
      {
        key: 'project_memberships',
        label: (count) => t('impactFields.projectMemberships', { count }),
      },
      {
        key: 'environment_memberships',
        label: (count) => t('impactFields.environmentMemberships', { count }),
      },
      {
        key: 'invitations',
        label: (count) => t('impactFields.invitations', { count }),
      },
    ];

  const PROJECT_IMPACT_FIELDS: ImpactField<ProjectDeletionImpact>[] = [
    {
      key: 'environments',
      label: (count) => t('impactFields.environments', { count }),
    },
    { key: 'flags', label: (count) => t('impactFields.flags', { count }) },
    {
      key: 'strategy_rules',
      label: (count) => t('impactFields.strategyRules', { count }),
    },
    {
      key: 'conditions',
      label: (count) => t('impactFields.conditions', { count }),
    },
    {
      key: 'overrides',
      label: (count) => t('impactFields.overrides', { count }),
    },
    {
      key: 'evaluation_logs',
      label: (count) => t('impactFields.evaluationLogs', { count }),
    },
    {
      key: 'sdk_registrations',
      label: (count) => t('impactFields.sdkRegistrations', { count }),
    },
    {
      key: 'project_memberships',
      label: (count) => t('impactFields.projectMemberships', { count }),
    },
    {
      key: 'environment_memberships',
      label: (count) => t('impactFields.environmentMemberships', { count }),
    },
  ];

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
              {t('brandName')}
            </span>
          </Link>

          <div className="flex items-center gap-2">
            {organizations.length > 1 ? (
              <select
                aria-label={t('organizationLabel')}
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
                aria-label={t('organizationLabel')}
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
                  title={t('createOrganizationTitle')}
                  className="gap-1.5 text-muted-foreground hover:text-foreground"
                />
              }
              triggerContent={
                <>
                  <Plus className="size-4" />
                  <span className="sr-only sm:not-sr-only">
                    {t('newOrganization')}
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
                title={t('renameOrganizationTitle')}
                description={t('renameOrganizationDescription')}
                toastMessage={t('renameOrganizationToast')}
                fields={[{ key: 'name', label: t('fieldNameLabel') }]}
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
                    <span className="sr-only">
                      {t('renameOrganizationTitle')}
                    </span>
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
                    ? t('deleteOrganizationBlocked', {
                        count: impact.other_members,
                      })
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
                    <span className="sr-only">{t('deleteOrganizationSr')}</span>
                  </>
                }
              />
            ) : null}

            <span aria-hidden="true" className="h-5 w-px bg-border" />

            {projects.length > 0 ? (
              <select
                aria-label={t('projectLabel')}
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
                    title={t('createProjectTitle')}
                    className="gap-1.5 text-muted-foreground hover:text-foreground"
                  />
                }
                triggerContent={
                  <>
                    <Plus className="size-4" />
                    <span className="sr-only sm:not-sr-only">
                      {t('newProject')}
                    </span>
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
                title={t('renameProjectTitle')}
                description={t('renameProjectDescription')}
                toastMessage={t('renameProjectToast')}
                fields={[
                  { key: 'name', label: t('fieldNameLabel') },
                  { key: 'key', label: t('fieldKeyLabel') },
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
                    <span className="sr-only">{t('renameProjectTitle')}</span>
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
                    <span className="sr-only">{t('deleteProjectSr')}</span>
                  </>
                }
              />
            ) : null}

            <LanguageSwitcher changeLocaleAction={changeLocaleAction} />

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
                  {t('logOut')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        <nav
          aria-label={t('navSectionsLabel')}
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
