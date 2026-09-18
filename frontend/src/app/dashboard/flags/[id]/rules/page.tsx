'use client';

import { ArrowLeft, Pencil, Plus, Trash2 } from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';
import { DataTableSkeleton } from '@/components/dashboard/skeletons/data-table-skeleton';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LoadingRegion } from '@/components/ui/loading-region';
import { PageHeader } from '@/components/ui/page-header';
import { Skeleton } from '@/components/ui/skeleton';
import { Slider } from '@/components/ui/slider';
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
  type Condition,
  conditionsApi,
  type FeatureFlag,
  flagsApi,
  rulesApi,
  type StrategyRule,
  variantsApi,
} from '@/lib/api';
import { useToast } from '@/lib/toast-context';

export default function RulesPage() {
  const t = useTranslations('flagRulesPage');
  const params = useParams();
  const router = useRouter();
  const { success, error: showError } = useToast();
  const flagId = params.id as string;

  // Translated labels can only be read inside the component, unlike the raw
  // `value`s below (which are the backend's enum and stay untranslated) --
  // see the same reasoning on `TABS` in `dashboard-nav.tsx`.
  const OPERATORS = [
    { value: 'EQUALS', label: t('operatorEquals') },
    { value: 'NOT_EQUALS', label: t('operatorNotEquals') },
    { value: 'GREATER_THAN', label: t('operatorGreaterThan') },
    { value: 'LESS_THAN', label: t('operatorLessThan') },
    { value: 'IN_LIST', label: t('operatorInList') },
    { value: 'CONTAINS', label: t('operatorContains') },
    { value: 'PERCENTAGE_SPLIT', label: t('operatorPercentageSplit') },
  ];

  const getOperatorLabel = (value: string) => {
    return OPERATORS.find((op) => op.value === value)?.label || value;
  };

  const [flag, setFlag] = useState<FeatureFlag | null>(null);
  const [rules, setRules] = useState<StrategyRule[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRuleDialogOpen, setIsRuleDialogOpen] = useState(false);
  const [isConditionDialogOpen, setIsConditionDialogOpen] = useState(false);
  const [selectedRule, setSelectedRule] = useState<StrategyRule | null>(null);
  const [editingRule, setEditingRule] = useState<StrategyRule | null>(null);
  const [editingCondition, setEditingCondition] = useState<Condition | null>(
    null,
  );
  const [isSaving, setIsSaving] = useState(false);
  const [newRule, setNewRule] = useState({
    priority: 1,
    operator_logic: 'AND' as 'AND' | 'OR',
    rollout_variant: '',
    rollout_percentage: '100',
  });
  const [newCondition, setNewCondition] = useState({
    attribute: '',
    operator: 'EQUALS',
    value: '',
  });
  type VariantDraft = {
    id: string;
    name: string;
    percentage_allocation: string;
    is_control: boolean;
  };

  const [isEditingVariants, setIsEditingVariants] = useState(false);
  const [variantDrafts, setVariantDrafts] = useState<VariantDraft[]>([]);
  const [isSavingVariants, setIsSavingVariants] = useState(false);

  const isVariantEditValid = variantDrafts.every(
    (row) => row.name.trim() !== '',
  );

  // The control variant is never edited directly: its percentage is always
  // `100 - sum(other variants)`, mirroring Flagsmith's variant editor.
  const recalcControlPercentage = (rows: VariantDraft[]): VariantDraft[] => {
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

  const getNonControlHeadroom = (rows: VariantDraft[], index: number) => {
    const otherNonControlSum = rows.reduce((sum, row, i) => {
      if (i === index || row.is_control) return sum;
      return sum + (Number(row.percentage_allocation) || 0);
    }, 0);
    return Math.max(0, 100 - otherNonControlSum);
  };

  const startEditingVariants = () => {
    if (!flag) return;
    setVariantDrafts(
      flag.variants.map((variant) => ({
        id: variant.id,
        name: variant.name,
        percentage_allocation: String(variant.percentage_allocation),
        is_control: variant.is_control,
      })),
    );
    setIsEditingVariants(true);
  };

  const updateVariantDraft = (
    index: number,
    patch: Partial<{
      name: string;
      percentage_allocation: string;
      is_control: boolean;
    }>,
  ) => {
    setVariantDrafts((rows) => {
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

  const handleSaveVariants = async () => {
    if (!flag || !isVariantEditValid) return;

    setIsSavingVariants(true);
    try {
      await variantsApi.replaceSet(
        flag.id,
        variantDrafts.map((row) => ({
          id: row.id,
          name: row.name,
          percentage_allocation: Number(row.percentage_allocation) || 0,
          is_control: row.is_control,
        })),
      );
      setIsEditingVariants(false);
      loadData();
      success(t('updateVariantsSuccessToast'));
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('updateVariantsErrorFallback'),
      );
    } finally {
      setIsSavingVariants(false);
    }
  };

  const loadData = useCallback(async () => {
    try {
      const [flagData, rulesData] = await Promise.all([
        flagsApi.get(flagId),
        rulesApi.list(flagId),
      ]);
      setFlag(flagData);
      setRules(rulesData.results);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [flagId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const resetRuleForm = () => {
    setEditingRule(null);
    setNewRule({
      priority: 1,
      operator_logic: 'AND',
      rollout_variant: '',
      rollout_percentage: '100',
    });
  };

  const handleEditRule = (rule: StrategyRule) => {
    setEditingRule(rule);
    setNewRule({
      priority: rule.priority,
      operator_logic: rule.operator_logic,
      rollout_variant: rule.rollout_variant ?? '',
      rollout_percentage: String(rule.rollout_percentage ?? 100),
    });
    setIsRuleDialogOpen(true);
  };

  const handleSaveRule = async () => {
    setIsSaving(true);
    try {
      const hasRollout =
        flag?.flag_type === 'MULTIVARIATE' && newRule.rollout_variant !== '';
      const payload = {
        priority: newRule.priority,
        operator_logic: newRule.operator_logic,
        rollout_variant: hasRollout ? newRule.rollout_variant : null,
        rollout_percentage: hasRollout
          ? Number(newRule.rollout_percentage) || 0
          : null,
      };
      if (editingRule) {
        await rulesApi.update(editingRule.id, payload);
        success(t('updateRuleSuccessToast'));
      } else {
        await rulesApi.create({ flag: flagId, ...payload });
        success(t('createRuleSuccessToast'));
      }
      setIsRuleDialogOpen(false);
      resetRuleForm();
      loadData();
    } catch (err) {
      showError(
        err instanceof Error
          ? err.message
          : editingRule
            ? t('updateRuleErrorFallback')
            : t('createRuleErrorFallback'),
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      await rulesApi.delete(ruleId);
      loadData();
      success(t('deleteRuleSuccessToast'));
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('deleteRuleErrorFallback'),
      );
    }
  };

  const handleAddCondition = (rule: StrategyRule) => {
    setSelectedRule(rule);
    setEditingCondition(null);
    setNewCondition({ attribute: '', operator: 'EQUALS', value: '' });
    setIsConditionDialogOpen(true);
  };

  const handleEditCondition = (condition: Condition) => {
    setEditingCondition(condition);
    let valueStr = '';
    if (Array.isArray(condition.value)) {
      valueStr = condition.value.join(', ');
    } else if (
      condition.operator === 'PERCENTAGE_SPLIT' &&
      typeof condition.value === 'object' &&
      condition.value !== null &&
      'value' in condition.value
    ) {
      valueStr = String((condition.value as { value: unknown }).value ?? '');
    } else {
      valueStr = String(condition.value);
    }
    setNewCondition({
      attribute: condition.attribute,
      operator: condition.operator,
      value: valueStr,
    });
    setIsConditionDialogOpen(true);
  };

  const handleCreateCondition = async () => {
    setIsSaving(true);
    try {
      let parsedValue: unknown = newCondition.value;
      if (newCondition.operator === 'IN_LIST') {
        parsedValue = newCondition.value.split(',').map((v) => v.trim());
      } else if (newCondition.operator === 'PERCENTAGE_SPLIT') {
        // Flagsmith-style % Split: the backend normalizes this into the
        // wrapped `{"value": N}` shape and validates the 0-100 range.
        // The attribute is meaningless here (the bucket comes from
        // `user_id` alone), so an untouched field sends the convention.
        parsedValue = { value: Number(newCondition.value) || 0 };
      } else if (
        ['GREATER_THAN', 'LESS_THAN'].includes(newCondition.operator)
      ) {
        parsedValue = Number(newCondition.value);
      }

      // A % Split needs no trait: the bucket comes from `user_id` alone.
      // An untouched attribute field sends that convention so the required
      // model field is never blank.
      const attribute =
        newCondition.operator === 'PERCENTAGE_SPLIT' &&
        newCondition.attribute.trim() === ''
          ? 'user_id'
          : newCondition.attribute;

      if (editingCondition) {
        await conditionsApi.update(editingCondition.id, {
          attribute,
          operator: newCondition.operator,
          value: parsedValue,
        });
        success(t('updateConditionSuccessToast'));
      } else if (selectedRule) {
        await conditionsApi.create({
          rule: selectedRule.id,
          attribute,
          operator: newCondition.operator,
          value: parsedValue,
        });
        success(t('createConditionSuccessToast'));
      }
      setIsConditionDialogOpen(false);
      setEditingCondition(null);
      setSelectedRule(null);
      loadData();
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('saveConditionErrorFallback'),
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteCondition = async (conditionId: string) => {
    try {
      await conditionsApi.delete(conditionId);
      loadData();
      success(t('deleteConditionSuccessToast'));
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('deleteConditionErrorFallback'),
      );
    }
  };

  if (isLoading) {
    // The back button navigates away regardless of whether `flag` has
    // loaded, so it renders for real here too, matching the resolved
    // layout below. The description interpolates `flag.key`, which is not
    // yet available -- so unlike the title, it stays a skeleton.
    return (
      <div className="space-y-6">
        <div className="flex items-start gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => router.push('/dashboard/flags')}
            aria-label={t('backToFlagsLabel')}
            className="mt-1 text-muted-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <PageHeader
            className="flex-1"
            title={t('pageTitle')}
            description={<Skeleton className="h-4 w-72" />}
          />
        </div>
        <LoadingRegion className="space-y-6">
          <Card>
            <CardContent>
              <DataTableSkeleton columns={4} />
            </CardContent>
          </Card>
        </LoadingRegion>
      </div>
    );
  }

  if (!flag) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        {t('flagNotFound')}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.push('/dashboard/flags')}
          aria-label={t('backToFlagsLabel')}
          className="mt-1 text-muted-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <PageHeader
          className="flex-1"
          title={t('pageTitle')}
          description={t.rich('pageDescription', {
            code: (chunks) => (
              <span className="font-mono text-foreground">{chunks}</span>
            ),
            flagKey: flag.key,
          })}
          action={
            <Dialog
              open={isRuleDialogOpen}
              onOpenChange={(open) => {
                setIsRuleDialogOpen(open);
                if (!open) resetRuleForm();
              }}
            >
              <DialogTrigger render={<Button />}>
                <Plus className="mr-2 h-4 w-4" />
                {t('newRuleButton')}
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle className="text-foreground">
                    {editingRule
                      ? t('editRuleDialogTitle')
                      : t('createRuleDialogTitle')}
                  </DialogTitle>
                  <DialogDescription className="text-muted-foreground">
                    {editingRule
                      ? t('editRuleDialogDescription')
                      : t('createRuleDialogDescription')}
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="priority" className="text-muted-foreground">
                      {t('priorityLabel')}
                    </Label>
                    <Input
                      id="priority"
                      type="number"
                      min="1"
                      value={newRule.priority}
                      onChange={(e) =>
                        setNewRule({
                          ...newRule,
                          priority: Number(e.target.value),
                        })
                      }
                      className="bg-muted border-border text-foreground"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="operator" className="text-muted-foreground">
                      {t('operatorLogicLabel')}
                    </Label>
                    <select
                      id="operator"
                      className="w-full p-2 border border-border rounded-md bg-muted text-foreground"
                      value={newRule.operator_logic}
                      onChange={(e) =>
                        setNewRule({
                          ...newRule,
                          operator_logic: e.target.value as 'AND' | 'OR',
                        })
                      }
                    >
                      <option value="AND">{t('operatorLogicAndOption')}</option>
                      <option value="OR">{t('operatorLogicOrOption')}</option>
                    </select>
                  </div>
                  {flag.flag_type === 'MULTIVARIATE' ? (
                    <div className="space-y-2">
                      <Label
                        htmlFor="rollout_variant"
                        className="text-muted-foreground"
                      >
                        {t('rolloutVariantLabel')}
                      </Label>
                      <select
                        id="rollout_variant"
                        className="w-full p-2 border border-border rounded-md bg-muted text-foreground"
                        value={newRule.rollout_variant}
                        onChange={(e) =>
                          setNewRule({
                            ...newRule,
                            rollout_variant: e.target.value,
                          })
                        }
                      >
                        <option value="">
                          {t('rolloutVariantNoneOption')}
                        </option>
                        {flag.variants.map((variant) => (
                          <option key={variant.id} value={variant.id}>
                            {variant.name}
                          </option>
                        ))}
                      </select>
                      {newRule.rollout_variant ? (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <Label
                              htmlFor="rollout_percentage"
                              className="text-muted-foreground"
                            >
                              {t('rolloutPercentageLabel')}
                            </Label>
                            <span className="font-mono text-sm text-foreground">
                              {newRule.rollout_percentage}%
                            </span>
                          </div>
                          <Slider
                            id="rollout_percentage"
                            min={0}
                            max={100}
                            value={[Number(newRule.rollout_percentage) || 0]}
                            onValueChange={(value) =>
                              setNewRule({
                                ...newRule,
                                rollout_percentage: String(
                                  Array.isArray(value) ? value[0] : value,
                                ),
                              })
                            }
                          />
                          <p className="text-xs text-muted-foreground/70">
                            {t('rolloutPercentageHint')}
                          </p>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setIsRuleDialogOpen(false);
                      resetRuleForm();
                    }}
                  >
                    {t('cancelButton')}
                  </Button>
                  <Button onClick={handleSaveRule} disabled={isSaving}>
                    {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
                    {editingRule ? t('updateButton') : t('createButton')}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          }
        />
      </div>

      {flag.flag_type === 'MULTIVARIATE' ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-lg text-foreground">
              {t('variantBreakdownTitle')}
            </CardTitle>
            {!isEditingVariants ? (
              <Button
                variant="outline"
                size="sm"
                onClick={startEditingVariants}
              >
                {t('editVariantsButton')}
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            {isEditingVariants ? (
              <div className="space-y-3">
                {variantDrafts.map((row, index) => (
                  <div key={row.id} className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Input
                        value={row.name}
                        onChange={(e) =>
                          updateVariantDraft(index, { name: e.target.value })
                        }
                      />
                      {row.is_control ? (
                        <span className="w-24 shrink-0 text-right font-mono text-sm text-muted-foreground">
                          {row.percentage_allocation}%
                        </span>
                      ) : (
                        <Input
                          type="number"
                          value={row.percentage_allocation}
                          onChange={(e) =>
                            updateVariantDraft(index, {
                              percentage_allocation: e.target.value,
                            })
                          }
                          min={0}
                          max={getNonControlHeadroom(variantDrafts, index)}
                          className="w-24"
                        />
                      )}
                    </div>
                    {row.is_control ? null : (
                      <Slider
                        min={0}
                        max={getNonControlHeadroom(variantDrafts, index)}
                        value={[Number(row.percentage_allocation) || 0]}
                        onValueChange={(value) =>
                          updateVariantDraft(index, {
                            percentage_allocation: String(
                              Array.isArray(value) ? value[0] : value,
                            ),
                          })
                        }
                      />
                    )}
                  </div>
                ))}
                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setIsEditingVariants(false)}
                  >
                    {t('cancelButton')}
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleSaveVariants}
                    disabled={isSavingVariants || !isVariantEditValid}
                  >
                    {isSavingVariants ? (
                      <Spinner size="sm" className="mr-2" />
                    ) : null}
                    {t('saveVariantsButton')}
                  </Button>
                </div>
              </div>
            ) : (
              <ul className="space-y-2">
                {flag.variants.map((variant) => (
                  <li
                    key={variant.id}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-foreground">
                      {variant.name}
                      {variant.is_control ? (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {t('variantControlBadge')}
                        </span>
                      ) : null}
                    </span>
                    <span className="font-mono text-muted-foreground">
                      {variant.percentage_allocation}%
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}

      {rules.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t('noRulesConfigured')}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {rules.map((rule) => (
            <Card key={rule.id}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <div>
                  <CardTitle className="text-lg text-foreground">
                    {t('rulePriorityTitle', { priority: rule.priority })}
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      ({rule.operator_logic})
                    </span>
                  </CardTitle>
                  <CardDescription className="text-muted-foreground">
                    {t('conditionsCountDescription', {
                      count: rule.conditions.length,
                    })}
                  </CardDescription>
                </div>
                <div className="flex space-x-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleAddCondition(rule)}
                  >
                    <Plus className="mr-1 h-4 w-4" />
                    {t('addConditionButton')}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleEditRule(rule)}
                    className="text-muted-foreground"
                    aria-label={t('editRuleAriaLabel', {
                      priority: rule.priority,
                    })}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDeleteRule(rule.id)}
                    className="text-muted-foreground hover:text-destructive hover:bg-muted"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {rule.conditions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    {t('noConditionsYet')}
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border">
                        <TableHead className="text-muted-foreground">
                          {t('attributeHeader')}
                        </TableHead>
                        <TableHead className="text-muted-foreground">
                          {t('operatorHeader')}
                        </TableHead>
                        <TableHead className="text-muted-foreground">
                          {t('valueHeader')}
                        </TableHead>
                        <TableHead className="text-muted-foreground w-[60px]"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rule.conditions.map((condition) => (
                        <TableRow key={condition.id} className="border-border">
                          <TableCell className="font-mono text-foreground">
                            {condition.attribute}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {getOperatorLabel(condition.operator)}
                          </TableCell>
                          <TableCell className="font-mono text-sm text-foreground">
                            {Array.isArray(condition.value)
                              ? condition.value.join(', ')
                              : condition.operator === 'PERCENTAGE_SPLIT' &&
                                  typeof condition.value === 'object' &&
                                  condition.value !== null &&
                                  'value' in condition.value
                                ? `${(condition.value as { value: unknown }).value}%`
                                : String(condition.value)}
                          </TableCell>
                          <TableCell>
                            <div className="flex space-x-1">
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => handleEditCondition(condition)}
                                className="text-muted-foreground"
                              >
                                <svg
                                  aria-hidden="true"
                                  className="h-4 w-4"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  stroke="currentColor"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                                  />
                                </svg>
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() =>
                                  handleDeleteCondition(condition.id)
                                }
                                className="text-muted-foreground hover:text-destructive hover:bg-muted"
                              >
                                <Trash2 className="h-4 w-4" />
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
          ))}
        </div>
      )}

      <Dialog
        open={isConditionDialogOpen}
        onOpenChange={(open) => {
          setIsConditionDialogOpen(open);
          if (!open) {
            setEditingCondition(null);
            setSelectedRule(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-foreground">
              {editingCondition
                ? t('editConditionDialogTitle')
                : t('addConditionDialogTitle')}
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">
              {editingCondition
                ? t('editConditionDialogDescription')
                : t('addConditionDialogDescription', {
                    priority: selectedRule?.priority ?? 0,
                  })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {newCondition.operator === 'PERCENTAGE_SPLIT' ? null : (
              <div className="space-y-2">
                <Label htmlFor="attribute" className="text-muted-foreground">
                  {t('attributeLabel')}
                </Label>
                <Input
                  id="attribute"
                  placeholder={t('attributePlaceholder')}
                  value={newCondition.attribute}
                  onChange={(e) =>
                    setNewCondition({
                      ...newCondition,
                      attribute: e.target.value,
                    })
                  }
                />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="operator" className="text-muted-foreground">
                {t('operatorLabel')}
              </Label>
              <select
                id="operator"
                className="w-full p-2 border border-border rounded-md bg-muted text-foreground"
                value={newCondition.operator}
                onChange={(e) =>
                  setNewCondition({ ...newCondition, operator: e.target.value })
                }
              >
                {OPERATORS.map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>
            </div>
            {newCondition.operator === 'PERCENTAGE_SPLIT' ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label
                    htmlFor="split_value"
                    className="text-muted-foreground"
                  >
                    {t('valueLabel')}
                  </Label>
                  <span className="font-mono text-sm text-foreground">
                    {Number(newCondition.value) || 0}%
                  </span>
                </div>
                <Slider
                  id="split_value"
                  min={0}
                  max={100}
                  value={[Number(newCondition.value) || 0]}
                  onValueChange={(value) =>
                    setNewCondition({
                      ...newCondition,
                      value: String(Array.isArray(value) ? value[0] : value),
                    })
                  }
                />
                <p className="text-xs text-muted-foreground/70">
                  {t('percentageSplitHint')}
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="value" className="text-muted-foreground">
                  {t('valueLabel')}
                </Label>
                <Input
                  id="value"
                  placeholder={
                    newCondition.operator === 'IN_LIST'
                      ? t('valuePlaceholderList')
                      : t('valuePlaceholderDefault')
                  }
                  value={newCondition.value}
                  onChange={(e) =>
                    setNewCondition({ ...newCondition, value: e.target.value })
                  }
                />
                {newCondition.operator === 'IN_LIST' && (
                  <p className="text-xs text-muted-foreground/70">
                    {t('inListHint')}
                  </p>
                )}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setIsConditionDialogOpen(false);
                setEditingCondition(null);
                setSelectedRule(null);
              }}
            >
              {t('cancelButton')}
            </Button>
            <Button onClick={handleCreateCondition} disabled={isSaving}>
              {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
              {editingCondition ? t('updateButton') : t('addButton')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
