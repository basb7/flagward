'use client';

import { Lock, MoreHorizontal, Plus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
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
import { PageHeader } from '@/components/ui/page-header';
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
  type Environment,
  environmentsApi,
  type FeatureFlag,
  flagsApi,
  overridesApi,
} from '@/lib/api';
import { useTenant } from '@/lib/tenant-context';
import { useToast } from '@/lib/toast-context';
import { cn } from '@/lib/utils';

export default function FlagsPage() {
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
  });

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

  const handleCreate = async () => {
    setIsSaving(true);
    try {
      await flagsApi.create(newFlag);
      setIsDialogOpen(false);
      setNewFlag({ environment: '', key: '', name: '', description: '' });
      loadData();
      success('Flag created successfully');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to create flag');
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
      setNewFlag({ environment: '', key: '', name: '', description: '' });
      loadData();
      success('Flag updated successfully');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to update flag');
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
      success(`Override lifted on ${flag.key}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to lift override');
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
      success(`Flag ${next ? 'enabled' : 'disabled'}`);
    } catch (err) {
      setFlagState(flag.id, !next);
      showError(err instanceof Error ? err.message : 'Failed to toggle flag');
    } finally {
      setTogglingFlagId(null);
    }
  };

  const deleteFlag = async (flagId: string) => {
    try {
      await flagsApi.delete(flagId);
      loadData();
      success('Flag deleted successfully');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to delete flag');
    }
  };

  const getEnvName = (envId: string) => {
    const env = environments.find((e) => e.id === envId);
    return env?.name || envId;
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Feature Flags"
        description="Manage your feature flags"
        action={
          <Dialog
            open={isDialogOpen}
            onOpenChange={(open) => {
              setIsDialogOpen(open);
              if (!open) {
                setEditingFlag(null);
                setNewFlag({
                  environment: '',
                  key: '',
                  name: '',
                  description: '',
                });
              }
            }}
          >
            <DialogTrigger render={<Button />}>
              <Plus className="mr-2 h-4 w-4" />
              New Flag
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="text-foreground">
                  {editingFlag ? 'Edit Feature Flag' : 'Create Feature Flag'}
                </DialogTitle>
                <DialogDescription className="text-muted-foreground">
                  {editingFlag
                    ? 'Update the feature flag details.'
                    : 'Add a new feature flag to control features.'}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label
                    htmlFor="environment"
                    className="text-muted-foreground"
                  >
                    Environment
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
                    <option value="">Select environment</option>
                    {environments.map((env) => (
                      <option key={env.id} value={env.id}>
                        {env.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="key" className="text-muted-foreground">
                    Key
                  </Label>
                  <Input
                    id="key"
                    placeholder="e.g., new-dashboard"
                    value={newFlag.key}
                    onChange={(e) =>
                      setNewFlag({ ...newFlag, key: e.target.value })
                    }
                    disabled={!!editingFlag}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="name" className="text-muted-foreground">
                    Name
                  </Label>
                  <Input
                    id="name"
                    placeholder="e.g., New Dashboard"
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
                    Description
                  </Label>
                  <Input
                    id="description"
                    placeholder="Optional description"
                    value={newFlag.description}
                    onChange={(e) =>
                      setNewFlag({ ...newFlag, description: e.target.value })
                    }
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setIsDialogOpen(false);
                    setEditingFlag(null);
                    setNewFlag({
                      environment: '',
                      key: '',
                      name: '',
                      description: '',
                    });
                  }}
                >
                  Cancel
                </Button>
                <Button
                  onClick={editingFlag ? handleUpdate : handleCreate}
                  disabled={isSaving}
                >
                  {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
                  {editingFlag ? 'Update' : 'Create'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-foreground">All Flags</CardTitle>
          <CardDescription className="text-muted-foreground">
            {flags.length} flag(s) configured
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="border-border">
                <TableHead className="w-[150px] text-muted-foreground">
                  Status
                </TableHead>
                <TableHead className="text-muted-foreground">Name</TableHead>
                <TableHead className="text-muted-foreground">Key</TableHead>
                <TableHead className="text-muted-foreground">
                  Environment
                </TableHead>
                <TableHead className="text-muted-foreground">Type</TableHead>
                <TableHead className="text-muted-foreground w-[100px]">
                  Actions
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
                        aria-label={`${flag.effective_is_enabled ? 'Disable' : 'Enable'} ${flag.key}`}
                      />
                      {flag.active_override ? (
                        <Badge
                          variant="warning"
                          title={`Forced ${flag.active_override.is_enabled ? 'on' : 'off'}: ${flag.active_override.reason}. Configured as ${flag.is_enabled ? 'enabled' : 'disabled'}.`}
                        >
                          <Lock className="size-3" />
                          Overridden
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
                          {flag.effective_is_enabled ? 'Enabled' : 'Disabled'}
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
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() =>
                            router.push(`/dashboard/flags/${flag.id}/rules`)
                          }
                        >
                          Rules
                        </DropdownMenuItem>
                        {flag.active_override ? (
                          <DropdownMenuItem onClick={() => liftOverride(flag)}>
                            Lift override
                          </DropdownMenuItem>
                        ) : null}
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => deleteFlag(flag.id)}
                        >
                          Delete
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
