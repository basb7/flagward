'use client';

import { Check, Copy, Plus, Trash2 } from 'lucide-react';
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
  type Environment,
  environmentsApi,
  type Project,
  projectsApi,
} from '@/lib/api';
import { useToast } from '@/lib/toast-context';

export default function EnvironmentsPage() {
  const { success, error: showError } = useToast();
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [newEnv, setNewEnv] = useState({ name: '', key: '', project: '' });
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadEnvironments = useCallback(async () => {
    try {
      const response = await environmentsApi.list();
      setEnvironments(response.results);
    } catch (error) {
      console.error('Failed to load environments:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadProjects = useCallback(async () => {
    try {
      const response = await projectsApi.list();
      setProjects(response.results);
      setNewEnv((current) =>
        current.project
          ? current
          : { ...current, project: response.results[0]?.id ?? '' },
      );
    } catch (error) {
      console.error('Failed to load projects:', error);
    }
  }, []);

  useEffect(() => {
    loadEnvironments();
    loadProjects();
  }, [loadEnvironments, loadProjects]);

  const handleCreate = async () => {
    if (!newEnv.project) return;
    setIsSaving(true);
    try {
      await environmentsApi.create(newEnv);
      setIsDialogOpen(false);
      setNewEnv({ name: '', key: '', project: newEnv.project });
      loadEnvironments();
      success('Environment created successfully');
    } catch (err) {
      showError(
        err instanceof Error ? err.message : 'Failed to create environment',
      );
    } finally {
      setIsSaving(false);
    }
  };

  const copyApiKey = (apiKey: string, id: string) => {
    navigator.clipboard.writeText(apiKey);
    setCopiedId(id);
    success('API key copied to clipboard');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const deleteEnvironment = async (envId: string) => {
    try {
      await environmentsApi.delete(envId);
      loadEnvironments();
      success('Environment deleted successfully');
    } catch (err) {
      showError(
        err instanceof Error ? err.message : 'Failed to delete environment',
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Environments"
        description="Manage your environments"
        action={
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger render={<Button />}>
              <Plus className="mr-2 h-4 w-4" />
              New Environment
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="text-foreground">
                  Create Environment
                </DialogTitle>
                <DialogDescription className="text-muted-foreground">
                  Add a new environment for your feature flags.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label
                    htmlFor="env-project"
                    className="text-muted-foreground"
                  >
                    Project
                  </Label>
                  <select
                    id="env-project"
                    className="h-9 w-full rounded-lg border border-border bg-muted px-2 text-sm text-foreground"
                    value={newEnv.project}
                    onChange={(e) =>
                      setNewEnv({ ...newEnv, project: e.target.value })
                    }
                  >
                    <option value="">Select a project</option>
                    {projects.map((proj) => (
                      <option key={proj.id} value={proj.id}>
                        {proj.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="name" className="text-muted-foreground">
                    Name
                  </Label>
                  <Input
                    id="name"
                    placeholder="e.g., Production"
                    value={newEnv.name}
                    onChange={(e) =>
                      setNewEnv({ ...newEnv, name: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="key" className="text-muted-foreground">
                    Key
                  </Label>
                  <Input
                    id="key"
                    placeholder="e.g., production"
                    value={newEnv.key}
                    onChange={(e) =>
                      setNewEnv({ ...newEnv, key: e.target.value })
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
                  onClick={handleCreate}
                  disabled={isSaving || !newEnv.project}
                >
                  {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
                  Create
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-foreground">All Environments</CardTitle>
          <CardDescription className="text-muted-foreground">
            {environments.length} environment(s) configured
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="border-border">
                <TableHead className="text-muted-foreground">Name</TableHead>
                <TableHead className="text-muted-foreground">Key</TableHead>
                <TableHead className="text-muted-foreground">API Key</TableHead>
                <TableHead className="text-muted-foreground w-[100px]">
                  Actions
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {environments.map((env) => (
                <TableRow key={env.id} className="border-border">
                  <TableCell className="font-medium text-foreground">
                    {env.name}
                  </TableCell>
                  <TableCell className="font-mono text-sm text-foreground">
                    {env.key}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center space-x-2">
                      <code className="text-xs bg-muted px-2 py-1 rounded text-foreground">
                        {env.api_key.slice(0, 16)}...
                      </code>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => copyApiKey(env.api_key, env.id)}
                        className="text-muted-foreground"
                      >
                        {copiedId === env.id ? (
                          <Check className="h-4 w-4 text-success" />
                        ) : (
                          <Copy className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex space-x-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground"
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => deleteEnvironment(env.id)}
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
        </CardContent>
      </Card>
    </div>
  );
}
