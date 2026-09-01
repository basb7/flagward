import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Button } from '@/components/ui/button';
import { RenameResourceDialog } from './rename-resource-dialog';

const success = vi.fn();
const showError = vi.fn();

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success, error: showError, info: vi.fn() }),
}));

const PROJECT_FIELDS = [
  { key: 'name', label: 'Name' },
  { key: 'key', label: 'Key' },
];

function setup(
  props: Partial<React.ComponentProps<typeof RenameResourceDialog>> = {},
) {
  const onSave = vi
    .fn<(values: Record<string, string>) => Promise<void>>()
    .mockResolvedValue();
  const onSaved = vi.fn();

  const utils = render(
    <RenameResourceDialog
      title="Rename project"
      description="The name and key both appear across the dashboard and API."
      toastMessage="Project renamed"
      triggerButton={<Button />}
      triggerContent="Rename"
      fields={PROJECT_FIELDS}
      initialValues={{ name: 'Mobile App', key: 'mobile-app' }}
      onSave={onSave}
      onSaved={onSaved}
      {...props}
    />,
  );

  return { ...utils, onSave, onSaved };
}

async function open() {
  fireEvent.click(screen.getByRole('button', { name: 'Rename' }));
  await waitFor(() =>
    expect(screen.getByLabelText('Name')).toBeInTheDocument(),
  );
}

const saveButton = () => screen.getByRole('button', { name: 'Save' });

beforeEach(() => {
  success.mockReset();
  showError.mockReset();
});

describe('RenameResourceDialog', () => {
  it('opens seeded with the current values', async () => {
    setup();
    await open();

    expect(screen.getByLabelText('Name')).toHaveValue('Mobile App');
    expect(screen.getByLabelText('Key')).toHaveValue('mobile-app');
  });

  it('disables Save while nothing has changed', async () => {
    // A no-op PATCH is a wasted round trip and a misleading "renamed" toast.
    setup();
    await open();

    expect(saveButton()).toBeDisabled();
  });

  it('enables Save once a field actually changes', async () => {
    setup();
    await open();

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Mobile App v2' },
    });

    expect(saveButton()).toBeEnabled();
  });

  it('disables Save again when the change is typed back to the original', async () => {
    setup();
    await open();

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Mobile App v2' },
    });
    expect(saveButton()).toBeEnabled();

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Mobile App' },
    });
    expect(saveButton()).toBeDisabled();
  });

  it('disables Save while a required field is empty', async () => {
    setup();
    await open();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: '' } });

    expect(saveButton()).toBeDisabled();
  });

  it('treats a whitespace-only field as empty', async () => {
    // A name of "   " is not a rename, it is a resource nobody can find
    // again in the switcher.
    setup();
    await open();

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: '   ' },
    });

    expect(saveButton()).toBeDisabled();
  });

  it('disables Save when any one of several fields is empty, not just the first', async () => {
    setup();
    await open();

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Mobile App v2' },
    });
    fireEvent.change(screen.getByLabelText('Key'), { target: { value: '' } });

    expect(saveButton()).toBeDisabled();
  });

  it('sends every field, changed or not, and reports success', async () => {
    const { onSave, onSaved } = setup();
    await open();

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Mobile App v2' },
    });
    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        name: 'Mobile App v2',
        key: 'mobile-app',
      }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(success).toHaveBeenCalledWith('Project renamed');
  });

  it('reports the backend message and does not claim success when saving fails', async () => {
    const { onSaved } = setup({
      onSave: vi
        .fn<(values: Record<string, string>) => Promise<void>>()
        .mockRejectedValue(new Error('A project with this key already exists')),
    });
    await open();

    fireEvent.change(screen.getByLabelText('Key'), {
      target: { value: 'taken' },
    });
    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(showError).toHaveBeenCalledWith(
        'A project with this key already exists',
      ),
    );
    expect(onSaved).not.toHaveBeenCalled();
    expect(success).not.toHaveBeenCalled();
  });

  it('re-seeds from the current values on reopen, discarding an abandoned edit', async () => {
    setup();
    await open();

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Abandoned' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() =>
      expect(screen.queryByLabelText('Name')).not.toBeInTheDocument(),
    );

    await open();

    expect(screen.getByLabelText('Name')).toHaveValue('Mobile App');
    expect(saveButton()).toBeDisabled();
  });

  it('works for a single-field resource such as an organization', async () => {
    setup({
      title: 'Rename organization',
      toastMessage: 'Organization renamed',
      fields: [{ key: 'name', label: 'Name' }],
      initialValues: { name: 'Acme Inc' },
    });
    await open();

    expect(saveButton()).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Acme Ltd' },
    });
    expect(saveButton()).toBeEnabled();
  });
});
