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
import { type Organization, tenancyApi } from '@/lib/api';
import { useToast } from '@/lib/toast-context';

/**
 * Creates the first organization on the dashboard's empty state, or another
 * one from the switcher -- both flows POST the same shape, so this dialog is
 * shared between them rather than duplicated. The caller becomes the new
 * organization's admin in the same backend transaction.
 */
export function CreateOrganizationDialog({
  triggerButton,
  triggerContent,
  onCreated,
}: {
  /** A `<Button ... />` element carrying only styling props, no children. */
  triggerButton: React.ReactElement;
  triggerContent: React.ReactNode;
  onCreated?: (organization: Organization) => void;
}) {
  const { success, error: showError } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [name, setName] = useState('');

  const handleCreate = async () => {
    setIsSaving(true);
    try {
      const organization = await tenancyApi.createOrganization({ name });
      setIsOpen(false);
      setName('');
      success('Organization created successfully');
      onCreated?.(organization);
    } catch (err) {
      showError(
        err instanceof Error ? err.message : 'Failed to create organization',
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
            Create organization
          </DialogTitle>
          <DialogDescription className="text-muted-foreground">
            You become its admin immediately.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="org-name" className="text-muted-foreground">
            Name
          </Label>
          <Input
            id="org-name"
            placeholder="e.g., Acme Inc"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
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
