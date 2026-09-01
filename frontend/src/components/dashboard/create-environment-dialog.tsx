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
import { type Environment, environmentsApi } from '@/lib/api';
import { useToast } from '@/lib/toast-context';

/**
 * Creates the first environment of a project, or another one from the
 * Environments page -- both flows POST the same shape, so this dialog is
 * shared between them rather than duplicated.
 *
 * Only the name is asked for: the server derives the environment's `key`
 * from it, and the SDKs authenticate with `api_key`, never the key. The key
 * stays writable on `PATCH /api/v1/environments/{id}/`, but no screen edits
 * it -- the rename dialog on the Environments page sends `name` alone, on
 * purpose. See `environmentsApi.updateEnvironment` for why.
 */
export function CreateEnvironmentDialog({
  projectId,
  triggerButton,
  triggerContent,
  onCreated,
}: {
  projectId: string;
  /** A `<Button ... />` element carrying only styling props, no children. */
  triggerButton: React.ReactElement;
  triggerContent: React.ReactNode;
  onCreated?: (environment: Environment) => void;
}) {
  const { success, error: showError } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [name, setName] = useState('');

  const handleCreate = async () => {
    setIsSaving(true);
    try {
      const environment = await environmentsApi.create({
        project: projectId,
        name,
      });
      setIsOpen(false);
      setName('');
      success('Environment created successfully');
      onCreated?.(environment);
    } catch (err) {
      showError(
        err instanceof Error ? err.message : 'Failed to create environment',
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
          <DialogTitle className="text-foreground">
            Create environment
          </DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Environments hold their own API key so an SDK can serve flags.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="environment-name" className="text-muted-foreground">
              Name
            </Label>
            <Input
              id="environment-name"
              placeholder="e.g., Production"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={isSaving || !name}>
            {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
