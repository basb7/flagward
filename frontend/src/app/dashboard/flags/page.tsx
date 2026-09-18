'use client';

import { Info, Lock, MoreHorizontal, Plus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LoadingRegion } from '@/components/ui/loading-region';
import { PageHeader } from '@/components/ui/page-header';
import { Slider } from '@/components/ui/slider';
import { Spinner } from '@/components/ui/spinner';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  type Environment,
  environmentsApi,
  type FeatureFlag,
  flagsApi,
  overridesApi,
  variantsApi,
} from '@/lib/api';
import { useTenant } from '@/lib/tenant-context';
import { useToast } from '@/lib/toast-context';
import { cn } from '@/lib/utils';

export default function FlagsPage() {
  const t = useTranslations('flagsPage');
  const router = useRouter();
  const { success, error: showError } = useToast();
  const { currentProject } = useTenant();
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingFlag, setEditingFlag] = useState<FeatureFlag | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [togglingFlagId, setTogglingFlagId] = useState<string | null>(null);
  const [newFlag, setNewFlag] = useState({
    environment: '',
    key: '',
    name: '',
    description: '',
    flag_type: 'BOOLEAN' as 'BOOLEAN' | 'MULTIVARIATE',
  });
  type VariantRow = {
    id: string;
    name: string;
    percentage_allocation: string;
    is_control: boolean;
  };

  const makeVariantRow = (
    overrides: Partial<{
      name: string;
      percentage_allocation: string;
      is_control: boolean;
    }> = {},
  ): VariantRow => ({
    id: crypto.randomUUID(),
    name: '',
    percentage_allocation: '0',
    is_control: false,
    ...overrides,
  });

  // The control variant is never edited directly: its percentage is always
  // `100 - sum(other variants)`, mirroring Flagsmith's variant editor.
  const recalcControlPercentage = (rows: VariantRow[]): VariantRow[] => {
    const controlIndex = rows.findIndex((row) => row.is_control);
    if (controlIndex === -1) return rows;
    const nonControlSum = rows.reduce(
      (sum, row, i) =>
        i === controlIndex
          ? sum
          : sum + (Number(row.percentage_allocation) || 0),
      0,
    );
    const controlValue = Math.max(0, Math.min(100, 100 - nonControlSum));
    return rows.map((row, i) =>
      i === controlIndex
        ? { ...row, percentage_allocation: String(controlValue) }
        : row,
    );
  };

  const getNonControlHeadroom = (rows: VariantRow[], index: number) => {
    const otherNonControlSum = rows.reduce((sum, row, i) => {
      if (i === index || row.is_control) return sum;
      return sum + (Number(row.percentage_allocation) || 0);
    }, 0);
    return Math.max(0, 100 - otherNonControlSum);
  };

  const [variantRows, setVariantRows] = useState<VariantRow[]>(() => [
    makeVariantRow({ is_control: true, percentage_allocation: '100' }),
    makeVariantRow(),
  ]);

  const resetFlagForm = () => {
    setNewFlag({
      environment: '',
      key: '',
      name: '',
      description: '',
      flag_type: 'BOOLEAN',
    });
    setVariantRows([
      makeVariantRow({ is_control: true, percentage_allocation: '100' }),
      makeVariantRow(),
    ]);
  };

  const addVariantRow = () => {
    setVariantRows((rows) =>
      recalcControlPercentage([...rows, makeVariantRow()]),
    );
  };

  const removeVariantRow = (index: number) => {
    setVariantRows((rows) => {
      const next = rows.filter((_, i) => i !== index);
      if (next.length > 0 && !next.some((row) => row.is_control)) {
        next[0].is_control = true;
      }
      return recalcControlPercentage(next);
    });
  };

  const updateVariantRow = (
    index: number,
    patch: Partial<{
      name: string;
      percentage_allocation: string;
      is_control: boolean;
    }>,
  ) => {
    setVariantRows((rows) => {
      const isControlRow = rows[index].is_control;
      const nextPatch =
        patch.percentage_allocation !== undefined && !isControlRow
          ? {
              ...patch,
              percentage_allocation: String(
                Math.max(
                  0,
                  Math.min(
                    Number(patch.percentage_allocation) || 0,
                    getNonControlHeadroom(rows, index),
                  ),
                ),
              ),
            }
          : patch;
      const next = rows.map((row, i) => {
        if (i === index) return { ...row, ...nextPatch };
        return row;
      });
      return recalcControlPercentage(next);
    });
  };

  const loadData = useCallback(async () => {
    try {
      const [flagsRes, envsRes] = await Promise.all([
        flagsApi.list({ project: currentProject?.id }),
        environmentsApi.list({ project: currentProject?.id }),
      ]);
      setFlags(flagsRes.results);
      setEnvironments(envsRes.results);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [currentProject]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const isMultivariateFormValid =
    newFlag.flag_type !== 'MULTIVARIATE' ||
    variantRows.every((row) => row.name.trim() !== '');

  const handleCreate = async () => {
    // Variants belong to the flag, but they're a separate API call after
    // `flagsApi.create` succeeds. Validating here, before that call, means an
    // invalid variant split never creates an orphaned flag that then blocks
    // retrying with the same key.
    if (!isMultivariateFormValid) {
      showError(t('createErrorFallback'));
      return;
    }

    setIsSaving(true);
    try {
      const createdFlag = await flagsApi.create(newFlag);
      if (newFlag.flag_type === 'MULTIVARIATE') {
        await variantsApi.bulkCreate(
          createdFlag.id,
          variantRows.map((row) => ({
            name: row.name,
            percentage_allocation: Number(row.percentage_allocation) || 0,
            is_control: row.is_control,
          })),
        );
      }
      setIsDialogOpen(false);
      resetFlagForm();
      loadData();
      success(t('createSuccessToast'));
    } catch (err) {
      showError(err instanceof Error ? err.message : t('createErrorFallback'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleEdit = (flag: FeatureFlag) => {
    setEditingFlag(flag);
    setNewFlag({
      environment: flag.environment,
      key: flag.key,
      name: flag.name,
      description: flag.description || '',
      flag_type: flag.flag_type,
    });
    setIsDialogOpen(true);
  };

  const handleUpdate = async () => {
    if (!editingFlag) return;

    setIsSaving(true);
    try {
      await flagsApi.update(editingFlag.id, {
        name: newFlag.name,
        description: newFlag.description,
      });
      setIsDialogOpen(false);
      setEditingFlag(null);
      resetFlagForm();
      loadData();
      success(t('updateSuccessToast'));
    } catch (err) {
      showError(err instanceof Error ? err.message : t('updateErrorFallback'));
    } finally {
      setIsSaving(false);
    }
  };

  const setFlagState = (flagId: string, isEnabled: boolean) => {
    setFlags((current) =>
      current.map((item) =>
        item.id === flagId
          ? { ...item, is_enabled: isEnabled, effective_is_enabled: isEnabled }
          : item,
      ),
    );
  };

  const liftOverride = async (flag: FeatureFlag) => {
    if (!flag.active_override) return;

    try {
      await overridesApi.lift(flag.active_override.id);
      loadData();
      success(t('liftOverrideSuccessToast', { key: flag.key }));
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('liftOverrideErrorFallback'),
      );
    }
  };

  const toggleFlag = async (flag: FeatureFlag) => {
    const next = !flag.is_enabled;

    // Move the switch immediately. Waiting for the round trip plus a full list
    // reload makes the control read as dead. Revert if the request fails.
    setTogglingFlagId(flag.id);
    setFlagState(flag.id, next);

    try {
      await flagsApi.update(flag.id, { is_enabled: next });
      success(
        t('toggleSuccessToast', { state: next ? 'enabled' : 'disabled' }),
      );
    } catch (err) {
      setFlagState(flag.id, !next);
      showError(err instanceof Error ? err.message : t('toggleErrorFallback'));
    } finally {
      setTogglingFlagId(null);
    }
  };

  const deleteFlag = async (flagId: string) => {
    try {
      await flagsApi.delete(flagId);
      loadData();
      success(t('deleteSuccessToast'));
    } catch (err) {
      showError(err instanceof Error ? err.message : t('deleteErrorFallback'));
    }
  };

  const getEnvName = (envId: string) => {
    const env = environments.find((e) => e.id === envId);
    return env?.name || envId;
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title={t('pageTitle')} description={t('pageDescription')} />
        <LoadingRegion className="space-y-6">
          <Card>
            <CardContent>
              <DataTableSkeleton columns={6} />
            </CardContent>
          </Card>
        </LoadingRegion>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('pageTitle')}
        description={t('pageDescription')}
        action={
          <Dialog
            open={isDialogOpen}
            onOpenChange={(open) => {
              setIsDialogOpen(open);
              if (!open) {
                setEditingFlag(null);
                resetFlagForm();
              }
            }}
          >
            <DialogTrigger render={<Button />}>
              <Plus className="mr-2 h-4 w-4" />
              {t('newFlagButton')}
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle className="text-foreground">
                  {editingFlag
                    ? t('editFlagDialogTitle')
                    : t('createFlagDialogTitle')}
                </DialogTitle>
                <DialogDescription className="text-muted-foreground">
                  {editingFlag
                    ? t('editFlagDialogDescription')
                    : t('createFlagDialogDescription')}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label
                    htmlFor="environment"
                    className="text-muted-foreground"
                  >
                    {t('environmentLabel')}
                  </Label>
                  <select
                    id="environment"
                    className="w-full p-2 border border-border rounded-md bg-muted text-foreground"
                    value={newFlag.environment}
                    onChange={(e) =>
                      setNewFlag({ ...newFlag, environment: e.target.value })
                    }
                    disabled={!!editingFlag}
                  >
                    <option value="">{t('selectEnvironmentOption')}</option>
                    {environments.map((env) => (
                      <option key={env.id} value={env.id}>
                        {env.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="key" className="text-muted-foreground">
                    {t('keyLabel')}
                  </Label>
                  <Input
                    id="key"
                    placeholder={t('keyPlaceholder')}
                    value={newFlag.key}
                    onChange={(e) =>
                      setNewFlag({ ...newFlag, key: e.target.value })
                    }
                    disabled={!!editingFlag}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="name" className="text-muted-foreground">
                    {t('nameLabel')}
                  </Label>
                  <Input
                    id="name"
                    placeholder={t('namePlaceholder')}
                    value={newFlag.name}
                    onChange={(e) =>
                      setNewFlag({ ...newFlag, name: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label
                    htmlFor="description"
                    className="text-muted-foreground"
                  >
                    {t('descriptionLabel')}
                  </Label>
                  <Input
                    id="description"
                    placeholder={t('descriptionPlaceholder')}
                    value={newFlag.description}
                    onChange={(e) =>
                      setNewFlag({ ...newFlag, description: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="flag_type" className="text-muted-foreground">
                    {t('flagTypeLabel')}
                  </Label>
                  <select
                    id="flag_type"
                    className="w-full p-2 border border-border rounded-md bg-muted text-foreground"
                    value={newFlag.flag_type}
                    onChange={(e) =>
                      setNewFlag({
                        ...newFlag,
                        flag_type: e.target.value as 'BOOLEAN' | 'MULTIVARIATE',
                      })
                    }
                    disabled={!!editingFlag}
                  >
                    <option value="BOOLEAN">
                      {t('flagTypeBooleanOption')}
                    </option>
                    <option value="MULTIVARIATE">
                      {t('flagTypeMultivariateOption')}
                    </option>
                  </select>
                </div>
                {!editingFlag && newFlag.flag_type === 'MULTIVARIATE' ? (
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">
                      {t('variantsSectionTitle')}
                    </Label>
                    <div className="space-y-2">
                      {variantRows.map((row, index) => (
                        <div key={row.id} className="space-y-1">
                          <div className="flex items-center gap-2">
                            <Input
                              placeholder={t('variantNamePlaceholder')}
                              value={row.name}
                              onChange={(e) =>
                                updateVariantRow(index, {
                                  name: e.target.value,
                                })
                              }
                            />
                            {row.is_control ? (
                              <span className="w-24 shrink-0 text-right font-mono text-sm text-muted-foreground">
                                {row.percentage_allocation}%
                              </span>
                            ) : (
                              <Input
                                type="number"
                                placeholder={t('variantPercentagePlaceholder')}
                                value={row.percentage_allocation}
                                onChange={(e) =>
                                  updateVariantRow(index, {
                                    percentage_allocation: e.target.value,
                                  })
                                }
                                min={0}
                                max={getNonControlHeadroom(variantRows, index)}
                                className="w-24"
                              />
                            )}
                            <Tooltip>
                              <TooltipTrigger
                                render={
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="size-6 text-muted-foreground"
                                    aria-label={t(
                                      'variantControlTooltipAriaLabel',
                                    )}
                                  />
                                }
                              >
                                <Info className="size-3.5" />
                              </TooltipTrigger>
                              <TooltipContent>
                                {t('variantControlTooltip')}
                              </TooltipContent>
                            </Tooltip>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => removeVariantRow(index)}
                              disabled={variantRows.length <= 1}
                              aria-label={t('removeVariantAriaLabel')}
                            >
                              &times;
                            </Button>
                          </div>
                          {row.is_control ? null : (
                            <Slider
                              min={0}
                              max={getNonControlHeadroom(variantRows, index)}
                              value={[Number(row.percentage_allocation) || 0]}
                              onValueChange={(value) =>
                                updateVariantRow(index, {
                                  percentage_allocation: String(
                                    Array.isArray(value) ? value[0] : value,
                                  ),
                                })
                              }
                            />
                          )}
                        </div>
                      ))}
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={addVariantRow}
                    >
                      {t('addVariantButton')}
                    </Button>
                  </div>
                ) : null}
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setIsDialogOpen(false);
                    setEditingFlag(null);
                    resetFlagForm();
                  }}
                >
                  {t('cancelButton')}
                </Button>
                <Button
                  onClick={editingFlag ? handleUpdate : handleCreate}
                  disabled={
                    isSaving || (!editingFlag && !isMultivariateFormValid)
                  }
                >
                  {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
                  {editingFlag ? t('updateButton') : t('createButton')}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-foreground">
            {t('allFlagsTitle')}
          </CardTitle>
          <CardDescription className="text-muted-foreground">
            {t('flagsCountDescription', { count: flags.length })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="border-border">
                <TableHead className="w-[150px] text-muted-foreground">
                  {t('statusHeader')}
                </TableHead>
                <TableHead className="text-muted-foreground">
                  {t('nameHeader')}
                </TableHead>
                <TableHead className="text-muted-foreground">
                  {t('keyHeader')}
                </TableHead>
                <TableHead className="text-muted-foreground">
                  {t('environmentHeader')}
                </TableHead>
                <TableHead className="text-muted-foreground">
                  {t('typeHeader')}
                </TableHead>
                <TableHead className="text-muted-foreground w-[100px]">
                  {t('actionsHeader')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {flags.map((flag) => (
                <TableRow key={flag.id} className="border-border">
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <Switch
                        checked={flag.effective_is_enabled}
                        disabled={
                          togglingFlagId === flag.id || !!flag.active_override
                        }
                        onCheckedChange={() => toggleFlag(flag)}
                        aria-label={t('toggleAriaLabel', {
                          action: flag.effective_is_enabled
                            ? 'disable'
                            : 'enable',
                          key: flag.key,
                        })}
                      />
                      {flag.active_override ? (
                        <Badge
                          variant="warning"
                          title={t('overriddenBadgeTitle', {
                            state: flag.active_override.is_enabled
                              ? 'on'
                              : 'off',
                            reason: flag.active_override.reason,
                            configured: flag.is_enabled
                              ? 'enabled'
                              : 'disabled',
                          })}
                        >
                          <Lock className="size-3" />
                          {t('overriddenBadge')}
                        </Badge>
                      ) : (
                        <span
                          className={cn(
                            'text-xs',
                            flag.effective_is_enabled
                              ? 'text-foreground'
                              : 'text-muted-foreground',
                          )}
                        >
                          {flag.effective_is_enabled
                            ? t('enabledStatus')
                            : t('disabledStatus')}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="font-medium text-foreground">
                    {flag.name}
                  </TableCell>
                  <TableCell className="font-mono text-sm text-foreground">
                    {flag.key}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {getEnvName(flag.environment)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {flag.flag_type}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-muted-foreground"
                          />
                        }
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleEdit(flag)}>
                          {t('editMenuItem')}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() =>
                            router.push(`/dashboard/flags/${flag.id}/rules`)
                          }
                        >
                          {t('rulesMenuItem')}
                        </DropdownMenuItem>
                        {flag.active_override ? (
                          <DropdownMenuItem onClick={() => liftOverride(flag)}>
                            {t('liftOverrideMenuItem')}
                          </DropdownMenuItem>
                        ) : null}
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => deleteFlag(flag.id)}
                        >
                          {t('deleteMenuItem')}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
