'use client';

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

export interface RenameField {
  key: string;
  label: string;
  placeholder?: string;
}

/**
 * A plain "edit these text fields" dialog, shared by organization and
 * project renaming -- both are a `PATCH` of one or two string fields with
 * nothing destructive about them, so unlike `DeleteResourceDialog` there is
 * no confirmation step here beyond the ordinary Save/Cancel.
 */
export function RenameResourceDialog({
  title,
  description,
  toastMessage,
  triggerButton,
  triggerContent,
  fields,
  initialValues,
  onSave,
  onSaved,
}: {
  title: string;
  description: string;
  /** Toast shown on success, e.g. "Organization renamed". */
  toastMessage: string;
  /** A `<Button ... />` element carrying only styling props, no children. */
  triggerButton: React.ReactElement;
  triggerContent: React.ReactNode;
  fields: RenameField[];
  /** Current values, keyed by field key. */
  initialValues: Record<string, string>;
  onSave: (values: Record<string, string>) => Promise<void>;
  /** Called after a successful save so the caller can refresh shared state. */
  onSaved: () => void;
}) {
  const { success, error: showError } = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(initialValues);

  // Re-seed only on the open transition, from whatever the caller currently
  // holds -- depending on initialValues would re-run on every parent render
  // and fight the user's own typing while the dialog is open.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see above
  useEffect(() => {
    if (isOpen) setValues(initialValues);
  }, [isOpen]);

  const hasEmptyRequiredField = fields.some(
    (field) => !values[field.key]?.trim(),
  );
  const isUnchanged = fields.every(
    (field) => values[field.key] === initialValues[field.key],
  );

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave(values);
      setIsOpen(false);
      success(toastMessage);
      onSaved();
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to save changes');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger render={triggerButton}>{triggerContent}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-foreground">{title}</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            {description}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {fields.map((field) => (
            <div key={field.key} className="space-y-2">
              <Label
                htmlFor={`rename-${field.key}`}
                className="text-muted-foreground"
              >
                {field.label}
              </Label>
              <Input
                id={`rename-${field.key}`}
                placeholder={field.placeholder}
                value={values[field.key] ?? ''}
                onChange={(e) =>
                  setValues({ ...values, [field.key]: e.target.value })
                }
              />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={isSaving || hasEmptyRequiredField || isUnchanged}
          >
            {isSaving ? <Spinner size="sm" className="mr-2" /> : null}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
