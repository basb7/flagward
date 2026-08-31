'use client';

import { TriangleAlert } from 'lucide-react';
import type * as React from 'react';
import { useEffect, useState } from 'react';
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
import { useToast } from '@/lib/toast-context';

export interface ImpactField<T extends Record<string, number>> {
  key: keyof T;
  /** Singular noun, e.g. "environment" -- pluralized for display when the count is not 1. */
  singular: string;
}

/**
 * The confirmation dialog for deleting an organization or a project. This is
 * the one place in the dashboard where "are you sure?" is not the question:
 * the dialog fetches and shows exactly what the delete would take with it,
 * requires the caller to type the resource's current name back (a checkbox
 * protects nobody -- it is set once and forgotten), and relays a backend
 * refusal (e.g. other members still on the organization) as something to go
 * do, not a bare "error".
 *
 * The field starts empty and nothing here fills it -- no default, no
 * placeholder. That is the whole protection: the person has to read the name
 * and decide.
 *
 * Pasting is allowed. Whether the characters arrive from a keyboard or a
 * clipboard does not change that someone read the name and acted, and
 * blocking it would make the most destructive action here hardest for the
 * people who most rely on paste -- assistive tech, dictation, limited motor
 * control -- while a drag-and-drop walks straight past the block anyway.
 */
export function DeleteResourceDialog<T extends Record<string, number>>({
  resourceLabel,
  resourceName,
  triggerButton,
  triggerContent,
  fetchImpact,
  impactFields,
  blockedWhen,
  onDelete,
  onDeleted,
}: {
  /** Lowercase noun used in copy, e.g. "organization" or "project". */
  resourceLabel: string;
  /** The exact current name the caller must retype to confirm. */
  resourceName: string;
  /** A `<Button ... />` element carrying only styling props, no children. */
  triggerButton: React.ReactElement;
  triggerContent: React.ReactNode;
  fetchImpact: () => Promise<T>;
  /** Which counts to show, in display order. Zero counts are omitted. */
  impactFields: ImpactField<T>[];
  /** Returns a reason deletion is refused given the fetched impact, or null when it is allowed. */
  blockedWhen?: (impact: T) => string | null;
  onDelete: (confirmName: string) => Promise<void>;
  /** Called after a successful delete so the caller can refresh shared state. */
  onDeleted: () => void;
}) {
  const { success } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [impact, setImpact] = useState<T | null>(null);
  const [isLoadingImpact, setIsLoadingImpact] = useState(false);
  const [impactError, setImpactError] = useState<string | null>(null);
  const [confirmValue, setConfirmValue] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // fetchImpact closes over the current resource id and is a fresh function
  // every render, and resourceLabel only affects an error message -- only
  // the open transition should trigger a fetch, not every re-render.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see above
  useEffect(() => {
    if (!isOpen) return;
    // Reset on every open, never carrying a stale value, count, or error
    // over from a previous look at this same dialog.
    setImpact(null);
    setImpactError(null);
    setConfirmValue('');
    setSubmitError(null);
    setIsLoadingImpact(true);
    fetchImpact()
      .then(setImpact)
      .catch((err) => {
        setImpactError(
          err instanceof Error
            ? err.message
            : `Failed to load what deleting this ${resourceLabel} would remove.`,
        );
      })
      .finally(() => setIsLoadingImpact(false));
  }, [isOpen]);

  const blockMessage = impact && blockedWhen ? blockedWhen(impact) : null;
  const nonZeroImpact = impact
    ? impactFields.filter((field) => impact[field.key] > 0)
    : [];
  const matches = confirmValue.length > 0 && confirmValue === resourceName;
  const canSubmit = !!impact && !blockMessage && matches && !isDeleting;

  const handleDelete = async () => {
    setIsDeleting(true);
    setSubmitError(null);
    try {
      await onDelete(confirmValue);
      setIsOpen(false);
      success(`${resourceName} deleted`);
      onDeleted();
    } catch (err) {
      // Stays open and shows exactly what the backend said -- a destructive
      // action that just says "error" reads as the product being broken.
      setSubmitError(
        err instanceof Error
          ? err.message
          : `Failed to delete this ${resourceLabel}.`,
      );
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger render={triggerButton}>{triggerContent}</DialogTrigger>
      <DialogContent className="border border-destructive/30 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <TriangleAlert className="size-4" />
            Delete {resourceLabel}
          </DialogTitle>
          <DialogDescription className="text-muted-foreground">
            This permanently deletes{' '}
            <span className="font-medium text-foreground">{resourceName}</span>{' '}
            and everything inside it. This cannot be undone.
          </DialogDescription>
        </DialogHeader>

        {isLoadingImpact ? (
          <div className="flex items-center justify-center py-6">
            <Spinner size="sm" />
          </div>
        ) : (
          <div className="space-y-4">
            {impactError ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {impactError}
              </div>
            ) : null}

            {impact ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
                {nonZeroImpact.length > 0 ? (
                  <>
                    <p className="mb-1.5 font-medium text-foreground">
                      This will also remove:
                    </p>
                    <ul className="list-inside list-disc space-y-0.5 text-muted-foreground">
                      {nonZeroImpact.map((field) => {
                        const count = impact[field.key];
                        return (
                          <li key={String(field.key)}>
                            {count}{' '}
                            {count === 1
                              ? field.singular
                              : `${field.singular}s`}
                          </li>
                        );
                      })}
                    </ul>
                  </>
                ) : (
                  <p className="text-muted-foreground">
                    Nothing else lives inside this {resourceLabel} yet.
                  </p>
                )}
              </div>
            ) : null}

            {blockMessage ? (
              <div className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
                {blockMessage}
              </div>
            ) : impact ? (
              <div className="space-y-2">
                <Label
                  htmlFor="delete-confirm-name"
                  className="text-muted-foreground"
                >
                  Type{' '}
                  <span className="font-medium text-foreground">
                    {resourceName}
                  </span>{' '}
                  to confirm
                </Label>
                <Input
                  id="delete-confirm-name"
                  autoComplete="off"
                  spellCheck={false}
                  value={confirmValue}
                  onChange={(e) => setConfirmValue(e.target.value)}
                />
                {/*
                  Pasting is allowed. The protection is that the field starts
                  empty and nothing here fills it: the person has to read the
                  name and decide. Whether the characters arrive from their
                  keyboard or their clipboard does not change that, and
                  blocking paste would make a destructive action hardest for
                  people who rely on it -- assistive tech, dictation, limited
                  motor control -- while a drag-and-drop still walks straight
                  past it. GitHub allows paste here too.

                  There is deliberately no placeholder either: showing the
                  name inside the field is one autofill away from filling it.
                */}
                <p className="text-xs text-muted-foreground">
                  Delete stays disabled until this matches the current name
                  exactly.
                </p>
              </div>
            ) : null}

            {submitError ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {submitError}
              </div>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            Cancel
          </Button>
          {!blockMessage ? (
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={!canSubmit}
            >
              {isDeleting ? <Spinner size="sm" className="mr-2" /> : null}
              Delete {resourceLabel}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
