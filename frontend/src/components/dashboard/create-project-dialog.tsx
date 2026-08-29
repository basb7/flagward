'use client';

import type * as React from 'react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
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
import { Spinner } from '@/components/ui/spinner';
import { type Project, tenancyApi } from '@/lib/api';
import { useToast } from '@/lib/toast-context';

/**
 * Creates the first project of an organization, or another one from the
 * dashboard switcher -- both flows POST the same shape, so this dialog is
 * shared between them rather than duplicated.
 */
export function CreateProjectDialog({
  organizationId,
  triggerButton,
  triggerContent,
  onCreated,
}: {
  organizationId: string;
  /** A `<Button ... />` element carrying only styling props, no children. */
  triggerButton: React.ReactElement;
  triggerContent: React.ReactNode;
  onCreated?: (project: Project) => void;
}) {
  const { success, error: showError } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState({ name: '', key: '' });

  const handleCreate = async () => {
    setIsSaving(true);
    try {
      const project = await tenancyApi.createProject({
        organization: organizationId,
        ...form,
      });
      setIsOpen(false);
      setForm({ name: '', key: '' });
      success('Project created successfully');
      onCreated?.(project);
    } catch (err) {
      showError(
        err instanceof Error ? err.message : 'Failed to create project',
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger render={triggerButton}>{triggerContent}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-foreground">Create project</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Environments, flags and API keys all live inside a project.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="project-name" className="text-muted-foreground">
              Name
            </Label>
            <Input
              id="project-name"
              placeholder="e.g., Mobile App"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="project-key" className="text-muted-foreground">
              Key
            </Label>
            <Input
              id="project-key"
              placeholder="e.g., mobile-app"
              value={form.key}
              onChange={(e) => setForm({ ...form, key: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={isSaving || !form.name || !form.key}
          >
            {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
