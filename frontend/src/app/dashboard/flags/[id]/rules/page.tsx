'use client';

import { ArrowLeft, Plus, Trash2 } from 'lucide-react';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';
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
  type Condition,
  conditionsApi,
  type FeatureFlag,
  flagsApi,
  rulesApi,
  type StrategyRule,
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
  const [editingCondition, setEditingCondition] = useState<Condition | null>(
    null,
  );
  const [isSaving, setIsSaving] = useState(false);
  const [newRule, setNewRule] = useState({
    priority: 1,
    operator_logic: 'AND' as 'AND' | 'OR',
  });
  const [newCondition, setNewCondition] = useState({
    attribute: '',
    operator: 'EQUALS',
    value: '',
  });

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

  const handleCreateRule = async () => {
    setIsSaving(true);
    try {
      await rulesApi.create({
        flag: flagId,
        priority: newRule.priority,
        operator_logic: newRule.operator_logic,
      });
      setIsRuleDialogOpen(false);
      setNewRule({ priority: 1, operator_logic: 'AND' });
      loadData();
      success(t('createRuleSuccessToast'));
    } catch (err) {
      showError(
        err instanceof Error ? err.message : t('createRuleErrorFallback'),
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
      } else if (
        ['GREATER_THAN', 'LESS_THAN'].includes(newCondition.operator)
      ) {
        parsedValue = Number(newCondition.value);
      }

      if (editingCondition) {
        await conditionsApi.update(editingCondition.id, {
          attribute: newCondition.attribute,
          operator: newCondition.operator,
          value: parsedValue,
        });
        success(t('updateConditionSuccessToast'));
      } else if (selectedRule) {
        await conditionsApi.create({
          rule: selectedRule.id,
          attribute: newCondition.attribute,
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
    return (
      <div className="flex justify-center items-center py-16">
        <Spinner size="lg" />
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
            <Dialog open={isRuleDialogOpen} onOpenChange={setIsRuleDialogOpen}>
              <DialogTrigger render={<Button />}>
                <Plus className="mr-2 h-4 w-4" />
                {t('newRuleButton')}
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle className="text-foreground">
                    {t('createRuleDialogTitle')}
                  </DialogTitle>
                  <DialogDescription className="text-muted-foreground">
                    {t('createRuleDialogDescription')}
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
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setIsRuleDialogOpen(false)}
                  >
                    {t('cancelButton')}
                  </Button>
                  <Button onClick={handleCreateRule} disabled={isSaving}>
                    {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
                    {t('createButton')}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          }
        />
      </div>

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
