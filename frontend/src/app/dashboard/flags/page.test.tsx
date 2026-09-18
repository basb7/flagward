import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithIntl } from '@/test/i18n';
import FlagsPage from './page';

// Mirrors the pattern in `environments/page.test.tsx`: mock the context
// hooks directly rather than mounting the real providers, so this test only
// pays for `FlagsPage`'s own render logic.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/lib/tenant-context', () => ({
  useTenant: () => ({ currentProject: { id: 'proj-1', name: 'Mobile' } }),
}));

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

const listFlags = vi.fn();
const listEnvironments = vi.fn();
const createFlag = vi.fn();
const bulkCreateVariants = vi.fn();

vi.mock('@/lib/api', () => ({
  flagsApi: {
    list: (...args: unknown[]) => listFlags(...args),
    create: (...args: unknown[]) => createFlag(...args),
  },
  environmentsApi: { list: (...args: unknown[]) => listEnvironments(...args) },
  overridesApi: { lift: vi.fn() },
  variantsApi: {
    bulkCreate: (...args: unknown[]) => bulkCreateVariants(...args),
  },
}));

describe('FlagsPage loading state', () => {
  it('renders the announcing skeleton region instead of the spinner while flags load', () => {
    listFlags.mockReturnValue(new Promise(() => {}));
    listEnvironments.mockReturnValue(new Promise(() => {}));

    renderWithIntl(<FlagsPage />);

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Feature Flags' }),
    ).toBeInTheDocument();
  });
});

describe('FlagsPage create dialog', () => {
  beforeEach(() => {
    listFlags.mockReset().mockResolvedValue({ results: [], count: 0 });
    listEnvironments.mockReset().mockResolvedValue({
      results: [{ id: 'env-1', name: 'Prod', key: 'prod', api_key: 'k' }],
      count: 1,
    });
    createFlag.mockReset();
    bulkCreateVariants.mockReset().mockResolvedValue([]);
  });

  const openCreateDialog = async () => {
    renderWithIntl(<FlagsPage />);
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /New Flag/i }),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /New Flag/i }));
  };

  it('defaults the flag type to Boolean and hides the variant editor', async () => {
    await openCreateDialog();

    const flagType = (await screen.findByLabelText(
      'Type',
    )) as HTMLSelectElement;
    expect(flagType.value).toBe('BOOLEAN');
    expect(screen.queryByText('Variants')).not.toBeInTheDocument();
  });

  it('shows the variant editor with two rows when Multivariate is selected', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    expect(screen.getByText('Variants')).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText('e.g., control')).toHaveLength(2);
  });

  it('warns when variant percentages do not sum to 100', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    const percentageInputs = screen.getAllByPlaceholderText('%');
    fireEvent.change(percentageInputs[0], { target: { value: '50' } });
    fireEvent.change(percentageInputs[1], { target: { value: '30' } });

    expect(screen.getByText(/must sum to 100/i)).toBeInTheDocument();
  });

  it('does not warn once variant percentages sum to 100', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    const percentageInputs = screen.getAllByPlaceholderText('%');
    fireEvent.change(percentageInputs[0], { target: { value: '60' } });
    fireEvent.change(percentageInputs[1], { target: { value: '40' } });

    expect(screen.queryByText(/must sum to 100/i)).not.toBeInTheDocument();
  });

  it('keeps exactly one control variant switch on at a time', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    const controlSwitches = screen.getAllByRole('switch', { name: 'Control' });
    expect(controlSwitches[0]).toHaveAttribute('aria-checked', 'true');
    expect(controlSwitches[1]).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(controlSwitches[1]);

    expect(controlSwitches[0]).toHaveAttribute('aria-checked', 'false');
    expect(controlSwitches[1]).toHaveAttribute('aria-checked', 'true');
  });

  it('creates a variant for each row after the flag is created', async () => {
    createFlag.mockResolvedValue({ id: 'flag-1' });
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Environment'), {
      target: { value: 'env-1' },
    });
    fireEvent.change(screen.getByLabelText('Key'), {
      target: { value: 'checkout-button' },
    });
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Checkout Button' },
    });
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    const nameInputs = screen.getAllByPlaceholderText('e.g., control');
    const percentageInputs = screen.getAllByPlaceholderText('%');
    fireEvent.change(nameInputs[0], { target: { value: 'control' } });
    fireEvent.change(percentageInputs[0], { target: { value: '50' } });
    fireEvent.change(nameInputs[1], { target: { value: 'treatment_a' } });
    fireEvent.change(percentageInputs[1], { target: { value: '50' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(bulkCreateVariants).toHaveBeenCalledTimes(1));
    expect(bulkCreateVariants).toHaveBeenCalledWith('flag-1', [
      { name: 'control', percentage_allocation: 50, is_control: true },
      { name: 'treatment_a', percentage_allocation: 50, is_control: false },
    ]);
  });

  it('does not create the flag at all when variant percentages are invalid', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Environment'), {
      target: { value: 'env-1' },
    });
    fireEvent.change(screen.getByLabelText('Key'), {
      target: { value: 'checkout-button' },
    });
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Checkout Button' },
    });
    fireEvent.change(screen.getByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    const nameInputs = screen.getAllByPlaceholderText('e.g., control');
    const percentageInputs = screen.getAllByPlaceholderText('%');
    fireEvent.change(nameInputs[0], { target: { value: 'control' } });
    fireEvent.change(percentageInputs[0], { target: { value: '50' } });
    fireEvent.change(nameInputs[1], { target: { value: 'treatment_a' } });
    fireEvent.change(percentageInputs[1], { target: { value: '30' } });

    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(createFlag).not.toHaveBeenCalled();
    expect(bulkCreateVariants).not.toHaveBeenCalled();
  });

  it('does not create variants for a Boolean flag', async () => {
    createFlag.mockResolvedValue({ id: 'flag-2' });
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Environment'), {
      target: { value: 'env-1' },
    });
    fireEvent.change(screen.getByLabelText('Key'), {
      target: { value: 'new-dashboard' },
    });
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'New Dashboard' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(createFlag).toHaveBeenCalledTimes(1));
    expect(bulkCreateVariants).not.toHaveBeenCalled();
  });
});
