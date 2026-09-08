'use client';

import { useTranslations } from 'next-intl';
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
 * stays writable on `PATCH /api/v1/environments/{id}/` -- there is simply no
 * screen editing it yet, unlike a project's.
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
  const t = useTranslations('createEnvironmentDialog');
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
      success(t('successToast'));
      onCreated?.(environment);
    } catch (err) {
      showError(err instanceof Error ? err.message : t('errorFallback'));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger render={triggerButton}>{triggerContent}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-foreground">{t('title')}</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            {t('description')}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="environment-name" className="text-muted-foreground">
              {t('nameLabel')}
            </Label>
            <Input
              id="environment-name"
              placeholder={t('namePlaceholder')}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            {t('cancel')}
          </Button>
          <Button onClick={handleCreate} disabled={isSaving || !name}>
            {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
            {t('create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
