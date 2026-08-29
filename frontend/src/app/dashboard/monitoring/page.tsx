'use client';

import {
  Activity,
  ChevronLeft,
  ChevronRight,
  Plug,
  RefreshCw,
  ShieldAlert,
  Zap,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Badge, StatusDot } from '@/components/ui/badge';
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
import { StatCard } from '@/components/ui/stat-card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  analyticsApi,
  type Environment,
  type EvaluationLog,
  environmentsApi,
  evaluationsApi,
  type FeatureFlag,
  type FlagOverride,
  flagsApi,
  overridesApi,
  type SDKHealth,
  type SDKRegistration,
  sdkRegistrationsApi,
} from '@/lib/api';
import { useTenant } from '@/lib/tenant-context';
import { useToast } from '@/lib/toast-context';
import { formatRelativeTime, formatTimestamp } from '@/lib/utils';

type Panel = 'sdks' | 'evaluations' | 'overrides';

const PANELS: { key: Panel; label: string }[] = [
  { key: 'sdks', label: 'SDKs' },
  { key: 'evaluations', label: 'Evaluations' },
  { key: 'overrides', label: 'Overrides' },
];

const RESULT_FILTERS = [
  { label: 'All', value: '' },
  { label: 'True', value: 'true' },
  { label: 'False', value: 'false' },
] as const;

function isStale(lastSeenAt: string, windowMinutes: number) {
  return Date.now() - Date.parse(lastSeenAt) > windowMinutes * 60_000;
}

export default function MonitoringPage() {
  const { success, error: showError } = useToast();
  const { currentProject } = useTenant();

  const [panel, setPanel] = useState<Panel>('sdks');
  const [environment, setEnvironment] = useState('');
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [flags, setFlags] = useState<FeatureFlag[]>([]);

  const [health, setHealth] = useState<SDKHealth | null>(null);
  const [registrations, setRegistrations] = useState<SDKRegistration[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationLog[]>([]);
  const [evaluationsCount, setEvaluationsCount] = useState(0);
  const [evaluationsPage, setEvaluationsPage] = useState(1);
  const [resultFilter, setResultFilter] = useState<string>('');
  const [flagFilter, setFlagFilter] = useState('');
  const [overrides, setOverrides] = useState<FlagOverride[]>([]);

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [liftingOverrideId, setLiftingOverrideId] = useState<string | null>(
    null,
  );
  const [newOverride, setNewOverride] = useState({
    flag: '',
    is_enabled: false,
    reason: '',
  });

  useEffect(() => {
    environmentsApi
      .list({ project: currentProject?.id })
      .then((response) =>
        setEnvironments(
          // The backend does not yet filter environments by `?project=`;
          // narrow client-side using the `project` field the serializer
          // already returns.
          currentProject
            ? response.results.filter(
                (env) => env.project === currentProject.id,
              )
            : response.results,
        ),
      )
      .catch(() => undefined);
  }, [currentProject]);

  const load = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const scope = environment ? { environment } : {};
      const [
        healthRes,
        registrationsRes,
        evaluationsRes,
        overridesRes,
        flagsRes,
      ] = await Promise.all([
        analyticsApi.sdkHealth({ ...scope, project: currentProject?.id }),
        sdkRegistrationsApi.list(scope),
        evaluationsApi.list({
          ...scope,
          page: evaluationsPage,
          ...(flagFilter ? { flag: flagFilter } : {}),
          ...(resultFilter ? { result: resultFilter === 'true' } : {}),
        }),
        overridesApi.list(scope),
        // Refetched here too: an override changes flag state, so a cached
        // flag list would keep showing the state the override just replaced.
        flagsApi.list({ project: currentProject?.id }),
      ]);

      setHealth(healthRes);
      setRegistrations(registrationsRes.results);
      setEvaluations(evaluationsRes.results);
      setEvaluationsCount(evaluationsRes.count);
      setOverrides(overridesRes.results);
      setFlags(flagsRes.results);
    } catch (err) {
      showError(
        err instanceof Error ? err.message : 'Failed to load monitoring data',
      );
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [
    environment,
    evaluationsPage,
    flagFilter,
    resultFilter,
    showError,
    currentProject,
  ]);

  useEffect(() => {
    load();
  }, [load]);

  // A new filter invalidates the current page, so reset both at once rather
  // than letting a fetch fire against the stale page number first.
  const applyFilter = (apply: () => void) => {
    apply();
    setEvaluationsPage(1);
  };

  const handleLiftOverride = async (override: FlagOverride) => {
    setLiftingOverrideId(override.id);
    try {
      await overridesApi.lift(override.id);
      await load();
      success(`Override lifted on ${override.flag_key}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to lift override');
    } finally {
      setLiftingOverrideId(null);
    }
  };

  const handleCreateOverride = async () => {
    setIsSaving(true);
    try {
      await overridesApi.create(newOverride);
      setIsDialogOpen(false);
      setNewOverride({ flag: '', is_enabled: false, reason: '' });
      await load();
      success('Override recorded and applied to the flag');
    } catch (err) {
      showError(
        err instanceof Error ? err.message : 'Failed to create override',
      );
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  const activeWindow = health?.active_window_minutes ?? 5;
  const evaluationsPageSize = 20;
  const lastPage = Math.max(
    1,
    Math.ceil(evaluationsCount / evaluationsPageSize),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Monitoring"
        description="Which SDKs are connected, what they evaluated, and every manual override."
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={load}
            disabled={isRefreshing}
          >
            <RefreshCw className={isRefreshing ? 'animate-spin' : undefined} />
            Refresh
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Environment"
          className="h-8 rounded-lg border border-border bg-card px-2 text-sm text-foreground"
          value={environment}
          onChange={(event) =>
            applyFilter(() => setEnvironment(event.target.value))
          }
        >
          <option value="">All environments</option>
          {environments.map((env) => (
            <option key={env.id} value={env.id}>
              {env.name}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5">
          {PANELS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setPanel(item.key)}
              aria-pressed={panel === item.key}
              className={
                panel === item.key
                  ? 'rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-foreground'
                  : 'rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground'
              }
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="SDKs active"
          value={health?.active ?? 0}
          hint={`Seen in the last ${activeWindow} min`}
          icon={Activity}
        />
        <StatCard
          label="SDKs stale"
          value={health?.stale ?? 0}
          hint={`${health?.total ?? 0} registered in total`}
          icon={Plug}
        />
        <StatCard
          label="Logged evaluations"
          value={evaluationsCount.toLocaleString()}
          hint="Matching the current filters"
          icon={Zap}
        />
      </div>

      {panel === 'sdks' ? (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Registered SDKs</CardTitle>
              <CardDescription>
                {registrations.length} instance(s). An SDK is stale after{' '}
                {activeWindow} minutes without polling.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {registrations.length === 0 ? (
                <EmptyState
                  icon={Plug}
                  title="No SDK has registered yet"
                  description="SDKs appear here after they call POST /api/v1/sdk/register/ with an environment API key."
                />
              ) : (
                <Table>
                  <TableHeader className="[&_th]:text-muted-foreground">
                    <TableRow>
                      <TableHead>Status</TableHead>
                      <TableHead>SDK</TableHead>
                      <TableHead>Version</TableHead>
                      <TableHead>Environment</TableHead>
                      <TableHead>SDK key</TableHead>
                      <TableHead>Last seen</TableHead>
                      <TableHead>Registered</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {registrations.map((registration) => {
                      const stale = isStale(
                        registration.last_seen_at,
                        activeWindow,
                      );
                      return (
                        <TableRow key={registration.id}>
                          <TableCell>
                            <Badge variant={stale ? 'warning' : 'success'}>
                              <StatusDot
                                tone={stale ? 'warning' : 'success'}
                                pulse={!stale}
                              />
                              {stale ? 'Stale' : 'Active'}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-medium text-foreground">
                            {registration.sdk_type}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {registration.version}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {registration.environment_name}
                          </TableCell>
                          <TableCell
                            className="max-w-32 truncate font-mono text-xs text-muted-foreground"
                            title={registration.sdk_key}
                          >
                            {registration.sdk_key}
                          </TableCell>
                          <TableCell
                            className="text-muted-foreground"
                            title={formatTimestamp(registration.last_seen_at)}
                          >
                            {formatRelativeTime(registration.last_seen_at)}
                          </TableCell>
                          <TableCell
                            className="text-muted-foreground"
                            title={formatTimestamp(registration.created_at)}
                          >
                            {formatRelativeTime(registration.created_at)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {health && health.by_version.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Versions in the fleet</CardTitle>
                <CardDescription>
                  Spot instances left behind on an old release.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-wrap gap-2">
                  {health.by_version.map((row) => (
                    <li key={`${row.sdk_type}-${row.version}`}>
                      <Badge variant="muted">
                        <span className="text-foreground">{row.sdk_type}</span>
                        <span className="font-mono">{row.version}</span>
                        <span className="tabular-nums">×{row.total}</span>
                      </Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}

      {panel === 'evaluations' ? (
        <Card>
          <CardHeader>
            <CardTitle>Evaluation log</CardTitle>
            <CardDescription>
              {evaluationsCount.toLocaleString()} evaluation(s) recorded. The
              context hash identifies a caller context without storing its
              attributes.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <select
                aria-label="Flag"
                className="h-8 rounded-lg border border-border bg-card px-2 text-sm text-foreground"
                value={flagFilter}
                onChange={(event) =>
                  applyFilter(() => setFlagFilter(event.target.value))
                }
              >
                <option value="">All flags</option>
                {flags.map((flag) => (
                  <option key={flag.id} value={flag.id}>
                    {flag.key}
                  </option>
                ))}
              </select>

              <div className="flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5">
                {RESULT_FILTERS.map((filter) => (
                  <button
                    key={filter.label}
                    type="button"
                    onClick={() =>
                      applyFilter(() => setResultFilter(filter.value))
                    }
                    aria-pressed={resultFilter === filter.value}
                    className={
                      resultFilter === filter.value
                        ? 'rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-foreground'
                        : 'rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground'
                    }
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
            </div>

            {evaluations.length === 0 ? (
              <EmptyState
                icon={Zap}
                title="No evaluations match these filters"
                description="Evaluations are recorded when an SDK calls POST /api/v1/sdk/evaluate/."
              />
            ) : (
              <>
                <Table>
                  <TableHeader className="[&_th]:text-muted-foreground">
                    <TableRow>
                      <TableHead>Result</TableHead>
                      <TableHead>Flag</TableHead>
                      <TableHead>Environment</TableHead>
                      <TableHead>Context hash</TableHead>
                      <TableHead>When</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {evaluations.map((log) => (
                      <TableRow key={log.id}>
                        <TableCell>
                          <Badge variant={log.result ? 'info' : 'muted'}>
                            {log.result ? 'true' : 'false'}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-foreground">
                          {log.flag_key}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {log.environment_key}
                        </TableCell>
                        <TableCell
                          className="max-w-32 truncate font-mono text-xs text-muted-foreground"
                          title={log.context_hash}
                        >
                          {log.context_hash}
                        </TableCell>
                        <TableCell
                          className="text-muted-foreground"
                          title={formatTimestamp(log.timestamp)}
                        >
                          {formatRelativeTime(log.timestamp)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted-foreground">
                    Page {evaluationsPage} of {lastPage}
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={evaluationsPage <= 1}
                      onClick={() => setEvaluationsPage((page) => page - 1)}
                    >
                      <ChevronLeft />
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={evaluationsPage >= lastPage}
                      onClick={() => setEvaluationsPage((page) => page + 1)}
                    >
                      Next
                      <ChevronRight />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      ) : null}

      {panel === 'overrides' ? (
        <Card>
          <CardHeader>
            <CardTitle>Override history</CardTitle>
            <CardDescription>
              While active, an override forces the flag's value and bypasses its
              targeting rules. Lifting one returns the flag to its configured
              state; the row stays here as the trail of who forced what and why.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Dialog
              open={isDialogOpen}
              onOpenChange={(open) => {
                setIsDialogOpen(open);
                if (!open) {
                  setNewOverride({ flag: '', is_enabled: false, reason: '' });
                }
              }}
            >
              <DialogTrigger render={<Button size="sm" />}>
                <ShieldAlert />
                New override
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Record an override</DialogTitle>
                  <DialogDescription>
                    This forces the flag immediately and supersedes any override
                    already active on it. The flag's own configuration is left
                    untouched, so lifting the override restores it.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="override-flag">Flag</Label>
                    <select
                      id="override-flag"
                      className="h-9 w-full rounded-lg border border-border bg-muted px-2 text-sm text-foreground"
                      value={newOverride.flag}
                      onChange={(event) =>
                        setNewOverride({
                          ...newOverride,
                          flag: event.target.value,
                        })
                      }
                    >
                      <option value="">Select a flag</option>
                      {flags.map((flag) => (
                        <option key={flag.id} value={flag.id}>
                          {flag.key} — {flag.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="override-state">New state</Label>
                    <select
                      id="override-state"
                      className="h-9 w-full rounded-lg border border-border bg-muted px-2 text-sm text-foreground"
                      value={newOverride.is_enabled ? 'enabled' : 'disabled'}
                      onChange={(event) =>
                        setNewOverride({
                          ...newOverride,
                          is_enabled: event.target.value === 'enabled',
                        })
                      }
                    >
                      <option value="disabled">Disabled (kill switch)</option>
                      <option value="enabled">Enabled</option>
                    </select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="override-reason">Reason</Label>
                    <Input
                      id="override-reason"
                      placeholder="e.g., payment provider outage"
                      value={newOverride.reason}
                      onChange={(event) =>
                        setNewOverride({
                          ...newOverride,
                          reason: event.target.value,
                        })
                      }
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setIsDialogOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleCreateOverride}
                    disabled={
                      isSaving || !newOverride.flag || !newOverride.reason
                    }
                  >
                    {isSaving ? <Spinner size="sm" /> : null}
                    Record override
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>

            {overrides.length === 0 ? (
              <EmptyState
                icon={ShieldAlert}
                title="No overrides recorded"
                description="Use an override when you need to force a flag on or off and leave a reason behind."
              />
            ) : (
              <Table>
                <TableHeader className="[&_th]:text-muted-foreground">
                  <TableRow>
                    <TableHead>Status</TableHead>
                    <TableHead>Forces</TableHead>
                    <TableHead>Flag</TableHead>
                    <TableHead>Environment</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>When</TableHead>
                    <TableHead className="w-[90px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {overrides.map((override) => (
                    <TableRow key={override.id}>
                      <TableCell>
                        {override.is_active ? (
                          <Badge variant="warning">
                            <StatusDot tone="warning" pulse />
                            Active
                          </Badge>
                        ) : (
                          <Badge
                            variant="muted"
                            title={
                              override.cleared_at
                                ? `Lifted ${formatTimestamp(override.cleared_at)}`
                                : undefined
                            }
                          >
                            Lifted
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={override.is_enabled ? 'success' : 'danger'}
                        >
                          {override.is_enabled ? 'On' : 'Off'}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-foreground">
                        {override.flag_key}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {override.environment_key}
                      </TableCell>
                      <TableCell
                        className="max-w-64 truncate"
                        title={override.reason}
                      >
                        {override.reason}
                      </TableCell>
                      <TableCell
                        className="text-muted-foreground"
                        title={formatTimestamp(override.created_at)}
                      >
                        {formatRelativeTime(override.created_at)}
                      </TableCell>
                      <TableCell>
                        {override.is_active ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={liftingOverrideId === override.id}
                            onClick={() => handleLiftOverride(override)}
                          >
                            {liftingOverrideId === override.id ? (
                              <Spinner size="sm" />
                            ) : null}
                            Lift
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
