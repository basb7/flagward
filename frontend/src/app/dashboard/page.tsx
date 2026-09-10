'use client';

import {
  Activity,
  Building2,
  Flag,
  Layers,
  Lock,
  Plus,
  ShieldAlert,
  Zap,
} from 'lucide-react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';
import { EvaluationsChart } from '@/components/charts/evaluations-chart';
import { CreateEnvironmentDialog } from '@/components/dashboard/create-environment-dialog';
import { CreateOrganizationDialog } from '@/components/dashboard/create-organization-dialog';
import { CreateProjectDialog } from '@/components/dashboard/create-project-dialog';
import { StatCardsSkeleton } from '@/components/dashboard/skeletons/stat-cards-skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingRegion } from '@/components/ui/loading-region';
import { PageHeader } from '@/components/ui/page-header';
import { Skeleton } from '@/components/ui/skeleton';
import { StatCard } from '@/components/ui/stat-card';
import {
  type AnalyticsOverview,
  analyticsApi,
  type Environment,
  type EvaluationsTimeseries,
  environmentsApi,
  type TopFlag,
} from '@/lib/api';
import { hasOrgCapability, useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useToast } from '@/lib/toast-context';

const RANGES = [
  { label: '6h', hours: 6 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
] as const;

function formatRate(rate: number | null) {
  return rate === null ? '—' : `${Math.round(rate * 100)}%`;
}

/**
 * The overview's loading shape: four stat cards, the 3/2 chart row and the
 * top-flags panel. Mirrors the real layout below so nothing shifts when the
 * data lands. Both the tenant load and the analytics load show the same page,
 * so they show the same skeleton. The page title/description render for real
 * above this (see both call sites below) rather than as part of it: they are
 * static translated strings available on first render, not data in flight.
 */
function OverviewSkeleton() {
  return (
    <LoadingRegion className="space-y-6">
      <StatCardsSkeleton count={4} />
      <div className="grid gap-4 lg:grid-cols-5">
        <Skeleton className="h-64 lg:col-span-3" />
        <Skeleton className="h-64 lg:col-span-2" />
      </div>
      <Skeleton className="h-40 w-full" />
    </LoadingRegion>
  );
}

export default function DashboardPage() {
  const t = useTranslations('dashboardHome');
  const { error: showError } = useToast();
  const { user } = useAuth();
  const {
    organizations,
    projects,
    currentOrganization,
    currentProject,
    setCurrentOrganization,
    isLoading: isTenantLoading,
    refresh,
  } = useTenant();
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [environment, setEnvironment] = useState('');
  const [hours, setHours] = useState<number>(24);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [timeseries, setTimeseries] = useState<EvaluationsTimeseries | null>(
    null,
  );
  const [topFlags, setTopFlags] = useState<TopFlag[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const loadEnvironments = useCallback(() => {
    environmentsApi
      .list({ project: currentProject?.id })
      .then((response) =>
        setEnvironments(
          // The backend does not yet filter environments by `?project=`
          // (that endpoint has no such filter today); narrow client-side
          // using the `project` field the serializer already returns.
          currentProject
            ? response.results.filter(
                (env) => env.project === currentProject.id,
              )
            : response.results,
        ),
      )
      .catch(() => setEnvironments([]));
  }, [currentProject]);

  useEffect(() => {
    loadEnvironments();
  }, [loadEnvironments]);

  const loadAnalytics = useCallback(async () => {
    try {
      const scope = {
        ...(environment ? { environment } : {}),
        ...(currentProject ? { project: currentProject.id } : {}),
      };
      const [overviewRes, timeseriesRes, topFlagsRes] = await Promise.all([
        analyticsApi.overview(scope),
        analyticsApi.evaluationsTimeseries({ ...scope, hours }),
        analyticsApi.topFlags({ ...scope, hours, limit: 5 }),
      ]);
      setOverview(overviewRes);
      setTimeseries(timeseriesRes);
      setTopFlags(topFlagsRes.results);
    } catch (err) {
      showError(
        err instanceof Error ? err.message : 'Failed to load analytics',
      );
    } finally {
      setIsLoading(false);
    }
  }, [environment, hours, showError, currentProject]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics]);

  if (isTenantLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('overviewTitle')}
          description={t('overviewDescription')}
        />
        <OverviewSkeleton />
      </div>
    );
  }

  if (organizations.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <EmptyState
          icon={Building2}
          title={t('createOrganizationTitle')}
          description={t('createOrganizationDescription')}
          action={
            <CreateOrganizationDialog
              triggerButton={<Button />}
              triggerContent={
                <>
                  <Plus className="mr-2 h-4 w-4" />
                  {t('createOrganizationButton')}
                </>
              }
              onCreated={async (organization) => {
                await refresh();
                setCurrentOrganization(organization);
              }}
            />
          }
        />
      </div>
    );
  }

  if (currentOrganization && projects.length === 0) {
    // Zero projects reads two different ways depending on what the caller
    // can do: nothing to see yet (offer to create one), or something exists
    // that this account has never been granted access to (a "Create" button
    // here would only 400 -- `project.create` is an organization-role grant,
    // never something a project- or environment-level role confers, so this
    // is the complete answer, not a guess).
    const canCreateProject = hasOrgCapability(
      user,
      currentOrganization.id,
      'project.create',
    );
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        {canCreateProject ? (
          <EmptyState
            icon={Layers}
            title={t('createProjectTitle')}
            description={t('createProjectDescription')}
            action={
              <CreateProjectDialog
                organizationId={currentOrganization.id}
                triggerButton={<Button />}
                triggerContent={
                  <>
                    <Plus className="mr-2 h-4 w-4" />
                    {t('createProjectButton')}
                  </>
                }
                onCreated={() => refresh()}
              />
            }
          />
        ) : (
          <EmptyState
            icon={Lock}
            title={t('noProjectAccessTitle')}
            description={t('noProjectAccessDescription', {
              organizationName: currentOrganization.name,
            })}
          />
        )}
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('overviewTitle')}
          description={t('overviewDescription')}
        />
        <OverviewSkeleton />
      </div>
    );
  }

  const maxTopFlagEvaluations = Math.max(
    ...topFlags.map((flag) => flag.evaluations),
    1,
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('overviewTitle')}
        description={t('overviewDescription')}
      />

      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label={t('environmentSelectLabel')}
          className="h-8 rounded-lg border border-border bg-card px-2 text-sm text-foreground"
          value={environment}
          onChange={(event) => setEnvironment(event.target.value)}
        >
          <option value="">{t('allEnvironmentsOption')}</option>
          {environments.map((env) => (
            <option key={env.id} value={env.id}>
              {env.name}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5">
          {RANGES.map((range) => (
            <button
              key={range.hours}
              type="button"
              onClick={() => setHours(range.hours)}
              aria-pressed={hours === range.hours}
              className={
                hours === range.hours
                  ? 'rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-foreground'
                  : 'rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground'
              }
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t('statFeatureFlagsLabel')}
          value={overview?.flags.total ?? 0}
          hint={
            overview?.flags.overridden
              ? t('statFeatureFlagsHintOverridden', {
                  trueCount: overview.flags.effective_enabled,
                  overriddenCount: overview.flags.overridden,
                })
              : t('statFeatureFlagsHintNormal', {
                  enabledCount: overview?.flags.enabled ?? 0,
                  disabledCount: overview?.flags.disabled ?? 0,
                })
          }
          icon={Flag}
          href="/dashboard/flags"
        />
        <StatCard
          label={t('statSdksLabel')}
          value={overview?.sdks.active ?? 0}
          hint={t('statSdksHint', {
            staleCount: overview?.sdks.stale ?? 0,
            totalCount: overview?.sdks.total ?? 0,
          })}
          icon={Activity}
          href="/dashboard/monitoring"
        />
        <StatCard
          label={t('statEvaluationsLabel')}
          value={(overview?.evaluations.last_24h ?? 0).toLocaleString()}
          hint={t('statEvaluationsHint', {
            rate: formatRate(overview?.evaluations.true_rate_24h ?? null),
          })}
          icon={Zap}
          href="/dashboard/monitoring"
        />
        <StatCard
          label={t('statOverridesLabel')}
          value={overview?.overrides.active ?? 0}
          hint={t('statOverridesHint', {
            totalCount: overview?.overrides.total ?? 0,
            last24hCount: overview?.overrides.last_24h ?? 0,
          })}
          icon={ShieldAlert}
          href="/dashboard/monitoring"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>{t('evaluationVolumeTitle')}</CardTitle>
            <CardDescription>
              {timeseries
                ? t('evaluationVolumeDescriptionData', {
                    formattedTotal: timeseries.total.toLocaleString(),
                    total: timeseries.total,
                    buckets: timeseries.buckets.length,
                  })
                : t('evaluationVolumeDescriptionEmpty')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {timeseries && timeseries.total > 0 ? (
              <EvaluationsChart buckets={timeseries.buckets} />
            ) : (
              <EmptyState
                icon={Zap}
                title={t('noEvaluationsTitle')}
                description={t('noEvaluationsDescription')}
              />
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t('mostEvaluatedTitle')}</CardTitle>
            <CardDescription>
              {t('lastHoursDescription', { hours })}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {topFlags.length === 0 ? (
              <EmptyState icon={Flag} title={t('noTrafficTitle')} />
            ) : (
              <ul className="space-y-3">
                {topFlags.map((flag) => (
                  <li key={flag.flag} className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <Link
                        href={`/dashboard/flags/${flag.flag}/rules`}
                        className="truncate font-mono text-xs text-foreground hover:underline"
                      >
                        {flag.flag_key}
                      </Link>
                      <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                        {flag.evaluations.toLocaleString()} ·{' '}
                        {formatRate(flag.true_rate)}
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-viz-true"
                        style={{
                          width: `${(flag.evaluations / maxTopFlagEvaluations) * 100}%`,
                        }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('environmentsCardTitle')}</CardTitle>
          <CardDescription>
            {t('environmentsCardDescription', {
              count: overview?.environments.total ?? 0,
            })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {environments.length === 0 ? (
            <EmptyState
              icon={Layers}
              title={t('noEnvironmentsTitle')}
              description={t('noEnvironmentsDescription')}
              action={
                currentProject ? (
                  <CreateEnvironmentDialog
                    projectId={currentProject.id}
                    triggerButton={<Button />}
                    triggerContent={
                      <>
                        <Plus className="mr-2 h-4 w-4" />
                        {t('createEnvironmentButton')}
                      </>
                    }
                    onCreated={loadEnvironments}
                  />
                ) : undefined
              }
            />
          ) : (
            <ul className="flex flex-wrap gap-2">
              {environments.map((env) => (
                <li key={env.id}>
                  <Link href="/dashboard/environments">
                    <Badge variant="muted" className="hover:text-foreground">
                      <span className="font-mono">{env.key}</span>
                      <span className="text-muted-foreground">{env.name}</span>
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
