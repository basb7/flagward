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
import { useCallback, useEffect, useState } from 'react';
import { EvaluationsChart } from '@/components/charts/evaluations-chart';
import { CreateOrganizationDialog } from '@/components/dashboard/create-organization-dialog';
import { CreateProjectDialog } from '@/components/dashboard/create-project-dialog';
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
import { PageHeader } from '@/components/ui/page-header';
import { Spinner } from '@/components/ui/spinner';
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

export default function DashboardPage() {
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

  useEffect(() => {
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
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  if (organizations.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <EmptyState
          icon={Building2}
          title="Create your organization"
          description="Everything in Flagward -- projects, environments and flags -- lives inside an organization. Name yours to get started."
          action={
            <CreateOrganizationDialog
              triggerButton={<Button />}
              triggerContent={
                <>
                  <Plus className="mr-2 h-4 w-4" />
                  Create organization
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
            title="Create your first project"
            description="Environments, flags and API keys all live inside a project."
            action={
              <CreateProjectDialog
                organizationId={currentOrganization.id}
                triggerButton={<Button />}
                triggerContent={
                  <>
                    <Plus className="mr-2 h-4 w-4" />
                    Create project
                  </>
                }
                onCreated={() => refresh()}
              />
            }
          />
        ) : (
          <EmptyState
            icon={Lock}
            title="No project access yet"
            description={`You have not been given access to any project in ${currentOrganization.name}. Ask an admin of this organization to grant you one.`}
          />
        )}
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
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
        title="Overview"
        description="Flag delivery, SDK fleet and evaluation traffic at a glance."
      />

      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Environment"
          className="h-8 rounded-lg border border-border bg-card px-2 text-sm text-foreground"
          value={environment}
          onChange={(event) => setEnvironment(event.target.value)}
        >
          <option value="">All environments</option>
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
          label="Feature flags"
          value={overview?.flags.total ?? 0}
          hint={
            overview?.flags.overridden
              ? `${overview.flags.effective_enabled} serving true · ${overview.flags.overridden} overridden`
              : `${overview?.flags.enabled ?? 0} enabled · ${overview?.flags.disabled ?? 0} disabled`
          }
          icon={Flag}
          href="/dashboard/flags"
        />
        <StatCard
          label="SDKs connected"
          value={overview?.sdks.active ?? 0}
          hint={`${overview?.sdks.stale ?? 0} stale of ${overview?.sdks.total ?? 0} registered`}
          icon={Activity}
          href="/dashboard/monitoring"
        />
        <StatCard
          label="Evaluations (24h)"
          value={(overview?.evaluations.last_24h ?? 0).toLocaleString()}
          hint={`${formatRate(overview?.evaluations.true_rate_24h ?? null)} served true`}
          icon={Zap}
          href="/dashboard/monitoring"
        />
        <StatCard
          label="Active overrides"
          value={overview?.overrides.active ?? 0}
          hint={`${overview?.overrides.total ?? 0} recorded · ${overview?.overrides.last_24h ?? 0} in the last 24h`}
          icon={ShieldAlert}
          href="/dashboard/monitoring"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Evaluation volume</CardTitle>
            <CardDescription>
              {timeseries
                ? `${timeseries.total.toLocaleString()} evaluations across ${timeseries.buckets.length} hourly buckets`
                : 'No data'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {timeseries && timeseries.total > 0 ? (
              <EvaluationsChart buckets={timeseries.buckets} />
            ) : (
              <EmptyState
                icon={Zap}
                title="No evaluations yet"
                description="Once an SDK calls the evaluate endpoint, traffic shows up here."
              />
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Most evaluated flags</CardTitle>
            <CardDescription>Last {hours}h</CardDescription>
          </CardHeader>
          <CardContent>
            {topFlags.length === 0 ? (
              <EmptyState icon={Flag} title="No traffic in this window" />
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
          <CardTitle>Environments</CardTitle>
          <CardDescription>
            {overview?.environments.total ?? 0} configured
          </CardDescription>
        </CardHeader>
        <CardContent>
          {environments.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="No environments yet"
              description="Create one to get an API key and start serving flags."
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
