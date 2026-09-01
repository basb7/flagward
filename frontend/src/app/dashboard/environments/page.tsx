'use client';

import {
  Building2,
  Check,
  Copy,
  Layers,
  Lock,
  Plus,
  Trash2,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { CreateEnvironmentDialog } from '@/components/dashboard/create-environment-dialog';
import { CreateProjectDialog } from '@/components/dashboard/create-project-dialog';
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { type Environment, environmentsApi } from '@/lib/api';
import { hasOrgCapability, useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useToast } from '@/lib/toast-context';

export default function EnvironmentsPage() {
  const { success, error: showError } = useToast();
  const { user } = useAuth();
  const {
    organizations,
    currentOrganization,
    currentProject,
    setCurrentProject,
    isLoading: isTenantLoading,
    refresh,
  } = useTenant();
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadEnvironments = useCallback(async () => {
    if (!currentProject) {
      setEnvironments([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const response = await environmentsApi.list({
        project: currentProject.id,
      });
      setEnvironments(response.results);
    } catch (error) {
      console.error('Failed to load environments:', error);
    } finally {
      setIsLoading(false);
    }
  }, [currentProject]);

  useEffect(() => {
    loadEnvironments();
  }, [loadEnvironments]);

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

  if (isTenantLoading) {
    return (
      <div className="flex justify-center items-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  if (organizations.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <EmptyState
          icon={Building2}
          title="Create your organization first"
          description="Environments live inside a project, and a project lives inside an organization."
          action={
            <Button render={<Link href="/dashboard" />}>Go to Overview</Button>
          }
        />
      </div>
    );
  }

  // Zero projects in the current organization: there is nothing here to list
  // yet, and the switcher's project control is hidden until a project
  // exists, so the action to fix that belongs here rather than only in the
  // nav -- see `hasOrgCapability` on `dashboard/page.tsx` for why creation is
  // an organization-role grant, never a project- or environment-level one.
  if (currentOrganization && !currentProject) {
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
            title="Create a project first"
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
                onCreated={(project) => {
                  refresh();
                  setCurrentProject(project);
                }}
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

  if (isLoading || !currentProject) {
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
          <CreateEnvironmentDialog
            projectId={currentProject.id}
            triggerButton={<Button />}
            triggerContent={
              <>
                <Plus className="mr-2 h-4 w-4" />
                New Environment
              </>
            }
            onCreated={loadEnvironments}
          />
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
          {environments.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="No environments yet"
              description="Create one to get an API key and start serving flags."
              action={
                <CreateEnvironmentDialog
                  projectId={currentProject.id}
                  triggerButton={<Button />}
                  triggerContent={
                    <>
                      <Plus className="mr-2 h-4 w-4" />
                      Create environment
                    </>
                  }
                  onCreated={loadEnvironments}
                />
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground">Name</TableHead>
                  <TableHead className="text-muted-foreground">Key</TableHead>
                  <TableHead className="text-muted-foreground">
                    API Key
                  </TableHead>
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
                        {/*
                          A bare icon has no accessible name at all, and this
                          is one of several identical copy buttons -- so the
                          name has to say *which* environment's key it copies.
                          It deliberately does not change when the icon flips
                          to the tick: the button still does the same thing,
                          and the success toast (which sonner renders in a
                          live region) is what announces that the copy
                          happened.
                        */}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => copyApiKey(env.api_key, env.id)}
                          aria-label={`Copy API key for ${env.name}`}
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
                          size="icon"
                          onClick={() => deleteEnvironment(env.id)}
                          aria-label={`Delete environment ${env.name}`}
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
    </div>
  );
}
