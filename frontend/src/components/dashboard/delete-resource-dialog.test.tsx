import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Button } from '@/components/ui/button';
import { DeleteResourceDialog } from './delete-resource-dialog';

const success = vi.fn();
const showError = vi.fn();

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success, error: showError, info: vi.fn() }),
}));

interface Impact extends Record<string, number> {
  environments: number;
  flags: number;
  other_members: number;
}

const IMPACT_FIELDS = [
  { key: 'environments' as const, singular: 'environment' },
  { key: 'flags' as const, singular: 'flag' },
];

function impact(overrides: Partial<Impact> = {}): Impact {
  return { environments: 0, flags: 0, other_members: 0, ...overrides };
}

function setup(
  props: Partial<
    React.ComponentProps<typeof DeleteResourceDialog<Impact>>
  > = {},
) {
  const fetchImpact = vi
    .fn<() => Promise<Impact>>()
    .mockResolvedValue(impact());
  const onDelete = vi.fn<(name: string) => Promise<void>>().mockResolvedValue();
  const onDeleted = vi.fn();

  const utils = render(
    <DeleteResourceDialog<Impact>
      resourceLabel="project"
      resourceName="Mobile App"
      triggerButton={<Button />}
      triggerContent="Delete"
      fetchImpact={fetchImpact}
      impactFields={IMPACT_FIELDS}
      onDelete={onDelete}
      onDeleted={onDeleted}
      {...props}
    />,
  );

  return { ...utils, fetchImpact, onDelete, onDeleted };
}

/** Opens the dialog and waits for the impact fetch to settle. */
async function open() {
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
  await waitFor(() =>
    expect(
      screen.getByRole('heading', { name: /Delete project/ }),
    ).toBeInTheDocument(),
  );
}

const confirmField = () => screen.getByLabelText(/to confirm/i);
const deleteButton = () =>
  screen.queryByRole('button', { name: 'Delete project' });

beforeEach(() => {
  success.mockReset();
  showError.mockReset();
});

describe('DeleteResourceDialog', () => {
  describe('the deletion_impact fetch', () => {
    it('fetches only on open, not on render', async () => {
      const { fetchImpact } = setup();
      expect(fetchImpact).not.toHaveBeenCalled();

      await open();

      await waitFor(() => expect(fetchImpact).toHaveBeenCalledTimes(1));
    });

    it('lists what the delete would take with it, omitting zero counts', async () => {
      setup({
        fetchImpact: vi
          .fn<() => Promise<Impact>>()
          .mockResolvedValue(impact({ environments: 2, flags: 0 })),
      });
      await open();

      await waitFor(() =>
        expect(screen.getByText('2 environments')).toBeInTheDocument(),
      );
      // A zero count is noise, not information.
      expect(screen.queryByText(/0 flags/)).not.toBeInTheDocument();
    });

    it('says so plainly when nothing lives inside the resource', async () => {
      setup();
      await open();

      await waitFor(() =>
        expect(
          screen.getByText(/Nothing else lives inside this project yet/i),
        ).toBeInTheDocument(),
      );
    });

    it('pluralizes only when the count is not 1', async () => {
      setup({
        fetchImpact: vi
          .fn<() => Promise<Impact>>()
          .mockResolvedValue(impact({ environments: 1, flags: 3 })),
      });
      await open();

      await waitFor(() =>
        expect(screen.getByText('1 environment')).toBeInTheDocument(),
      );
      expect(screen.getByText('3 flags')).toBeInTheDocument();
    });

    it('blocks the submit path while the impact has not loaded', async () => {
      // A delete that fires before its own impact is known defeats the
      // whole point of showing one.
      let resolveImpact: (value: Impact) => void = () => {};
      setup({
        fetchImpact: vi.fn<() => Promise<Impact>>().mockReturnValue(
          new Promise<Impact>((resolve) => {
            resolveImpact = resolve;
          }),
        ),
      });
      await open();

      // While loading there is no confirm field to type into at all.
      expect(screen.queryByLabelText(/to confirm/i)).not.toBeInTheDocument();
      expect(deleteButton()).toBeDisabled();

      resolveImpact(impact());
      await waitFor(() => expect(confirmField()).toBeInTheDocument());
    });

    it('surfaces the fetch failure and still refuses to delete', async () => {
      setup({
        fetchImpact: vi
          .fn<() => Promise<Impact>>()
          .mockRejectedValue(new Error('deletion_impact is unavailable')),
      });
      await open();

      await waitFor(() =>
        expect(
          screen.getByText('deletion_impact is unavailable'),
        ).toBeInTheDocument(),
      );
      expect(screen.queryByLabelText(/to confirm/i)).not.toBeInTheDocument();
      expect(deleteButton()).toBeDisabled();
    });

    it('re-fetches on every open and forgets the previous attempt', async () => {
      const fetchImpact = vi
        .fn<() => Promise<Impact>>()
        .mockResolvedValue(impact());
      const { onDelete } = setup({ fetchImpact });

      await open();
      fireEvent.change(confirmField(), { target: { value: 'Mobile App' } });
      await waitFor(() => expect(deleteButton()).toBeEnabled());
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

      await waitFor(() =>
        expect(
          screen.queryByRole('heading', { name: /Delete project/ }),
        ).not.toBeInTheDocument(),
      );
      await open();

      await waitFor(() => expect(fetchImpact).toHaveBeenCalledTimes(2));
      // The typed confirmation must not survive: a second open is a second
      // decision, and a pre-armed Delete button is exactly what this dialog
      // exists to prevent.
      expect(confirmField()).toHaveValue('');
      expect(deleteButton()).toBeDisabled();
      expect(onDelete).not.toHaveBeenCalled();
    });
  });

  describe('the confirm-by-typing-the-name gate', () => {
    it('starts empty and keeps Delete disabled', async () => {
      setup();
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      expect(confirmField()).toHaveValue('');
      expect(deleteButton()).toBeDisabled();
    });

    it('stays disabled for a near miss, and for case or whitespace differences', async () => {
      setup();
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      for (const nearMiss of [
        'Mobile',
        'Mobile App ',
        ' Mobile App',
        'mobile app',
        'MOBILE APP',
        'Mobile  App',
        'Mobile Apps',
      ]) {
        fireEvent.change(confirmField(), { target: { value: nearMiss } });
        expect(deleteButton()).toBeDisabled();
      }
    });

    it('enables Delete only on an exact match', async () => {
      setup();
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      fireEvent.change(confirmField(), { target: { value: 'Mobile App' } });

      expect(deleteButton()).toBeEnabled();
    });

    it('disables Delete again when the match is edited away', async () => {
      setup();
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      fireEvent.change(confirmField(), { target: { value: 'Mobile App' } });
      expect(deleteButton()).toBeEnabled();

      fireEvent.change(confirmField(), { target: { value: 'Mobile Ap' } });
      expect(deleteButton()).toBeDisabled();
    });

    it('allows pasting the name', async () => {
      // Deliberate: whether the characters arrive from a keyboard or a
      // clipboard does not change that someone read the name and acted, and
      // blocking paste would make the most destructive action here hardest
      // for the people who most rely on it. If an onPaste handler ever
      // starts calling preventDefault, this goes red.
      setup();
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      const pasteWasAllowed = fireEvent.paste(confirmField(), {
        clipboardData: { getData: () => 'Mobile App' },
      });
      expect(pasteWasAllowed).toBe(true);

      fireEvent.change(confirmField(), { target: { value: 'Mobile App' } });
      expect(deleteButton()).toBeEnabled();
    });

    it('does not put the name in a placeholder', async () => {
      // Deliberate: a placeholder showing the name is one autofill away from
      // filling the field the person is supposed to fill themselves.
      setup();
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      expect(confirmField()).not.toHaveAttribute('placeholder');
    });

    it('passes the typed name to onDelete, then reports success', async () => {
      const { onDelete, onDeleted } = setup();
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      fireEvent.change(confirmField(), { target: { value: 'Mobile App' } });
      fireEvent.click(deleteButton() as HTMLElement);

      await waitFor(() => expect(onDelete).toHaveBeenCalledWith('Mobile App'));
      await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
      expect(success).toHaveBeenCalledWith('Mobile App deleted');
    });

    it('stays open and shows what the backend said when the delete fails', async () => {
      // A destructive action that just says "error" reads as the product
      // being broken, and closing the dialog hides the reason entirely.
      const { onDeleted } = setup({
        onDelete: vi
          .fn<(name: string) => Promise<void>>()
          .mockRejectedValue(new Error('Remove the other members first.')),
      });
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      fireEvent.change(confirmField(), { target: { value: 'Mobile App' } });
      fireEvent.click(deleteButton() as HTMLElement);

      await waitFor(() =>
        expect(
          screen.getByText('Remove the other members first.'),
        ).toBeInTheDocument(),
      );
      expect(
        screen.getByRole('heading', { name: /Delete project/ }),
      ).toBeInTheDocument();
      expect(onDeleted).not.toHaveBeenCalled();
      expect(success).not.toHaveBeenCalled();
    });
  });

  describe('when deletion is blocked', () => {
    const blockedWhen = (value: Impact) =>
      value.other_members > 0
        ? `This organization has ${value.other_members} other member(s); remove them first before deleting it.`
        : null;

    it('does not render the delete button at all', async () => {
      // Not "disabled": absent. A blocked delete is not a thing the person
      // can complete by trying harder, so offering the control at all only
      // invites the click that will be refused.
      setup({
        fetchImpact: vi
          .fn<() => Promise<Impact>>()
          .mockResolvedValue(impact({ other_members: 2 })),
        blockedWhen,
      });
      await open();

      await waitFor(() =>
        expect(
          screen.getByText(/has 2 other member\(s\)/i),
        ).toBeInTheDocument(),
      );
      expect(deleteButton()).not.toBeInTheDocument();
    });

    it('does not offer the confirm field either', async () => {
      setup({
        fetchImpact: vi
          .fn<() => Promise<Impact>>()
          .mockResolvedValue(impact({ other_members: 2 })),
        blockedWhen,
      });
      await open();

      await waitFor(() =>
        expect(
          screen.getByText(/has 2 other member\(s\)/i),
        ).toBeInTheDocument(),
      );
      expect(screen.queryByLabelText(/to confirm/i)).not.toBeInTheDocument();
    });

    it('keeps the delete available when the block condition does not hold', async () => {
      setup({
        fetchImpact: vi
          .fn<() => Promise<Impact>>()
          .mockResolvedValue(impact({ other_members: 0 })),
        blockedWhen,
      });
      await open();
      await waitFor(() => expect(confirmField()).toBeInTheDocument());

      fireEvent.change(confirmField(), { target: { value: 'Mobile App' } });

      expect(deleteButton()).toBeEnabled();
    });
  });
});
