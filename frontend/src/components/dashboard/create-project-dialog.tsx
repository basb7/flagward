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
import { type Project, tenancyApi } from '@/lib/api';
import { useErrorCopy } from '@/lib/error-copy';
import { useToast } from '@/lib/toast-context';

/**
 * Creates the first project of an organization, or another one from the
 * dashboard switcher -- both flows POST the same shape, so this dialog is
 * shared between them rather than duplicated.
 *
 * Only the name is asked for: the server derives the project's `key` from it
 * and nothing resolves that key anyway. It stays editable afterwards in the
 * rename dialog for anyone who wants a different one.
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
  const t = useTranslations('createProjectDialog');
  const { success, error: showError } = useToast();
  const errorCopy = useErrorCopy();
  const [isOpen, setIsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [name, setName] = useState('');

  const handleCreate = async () => {
    setIsSaving(true);
    try {
      const project = await tenancyApi.createProject({
        organization: organizationId,
        name,
      });
      setIsOpen(false);
      setName('');
      success(t('successToast'));
      onCreated?.(project);
    } catch (err) {
      showError(
        err instanceof Error ? errorCopy(err.message) : t('errorFallback'),
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
          <DialogTitle className="text-foreground">{t('title')}</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            {t('description')}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="project-name" className="text-muted-foreground">
              {t('nameLabel')}
            </Label>
            <Input
              id="project-name"
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
