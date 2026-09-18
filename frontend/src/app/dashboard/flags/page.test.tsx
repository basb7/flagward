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

  it('shows the variant editor with two rows, control defaulting to 100%', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    expect(screen.getByText('Variants')).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText('e.g., control')).toHaveLength(2);
    // The control row is read-only text; only the treatment row has an input.
    const percentageInputs = screen.getAllByPlaceholderText('%');
    expect(percentageInputs).toHaveLength(1);
    expect(percentageInputs[0]).toHaveValue(0);
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(
      screen.queryByRole('switch', { name: 'Control' }),
    ).not.toBeInTheDocument();
  });

  it('recalculates the control percentage automatically as another variant changes', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    const percentageInputs = screen.getAllByPlaceholderText('%');
    fireEvent.change(percentageInputs[0], { target: { value: '30' } });

    expect(screen.getByText('70%')).toBeInTheDocument();
    expect(screen.queryByText(/must sum to 100/i)).not.toBeInTheDocument();
  });

  it('clamps a variant percentage so the total can never exceed 100', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Add variant/i }));

    const percentageInputs = screen.getAllByPlaceholderText('%');
    fireEvent.change(percentageInputs[0], { target: { value: '90' } });
    expect(screen.getByText('10%')).toBeInTheDocument();

    fireEvent.change(percentageInputs[1], { target: { value: '50' } });

    expect(percentageInputs[1]).toHaveValue(10);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('shows the control percentage as read-only text with no switch', async () => {
    await openCreateDialog();

    fireEvent.change(await screen.findByLabelText('Type'), {
      target: { value: 'MULTIVARIATE' },
    });

    // Control is always the default: no switch, derived percentage as text.
    expect(
      screen.queryByRole('switch', { name: 'Control' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
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
    fireEvent.change(nameInputs[1], { target: { value: 'treatment_a' } });
    fireEvent.change(percentageInputs[0], { target: { value: '50' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(bulkCreateVariants).toHaveBeenCalledTimes(1));
    expect(bulkCreateVariants).toHaveBeenCalledWith('flag-1', [
      { name: 'control', percentage_allocation: 50, is_control: true },
      { name: 'treatment_a', percentage_allocation: 50, is_control: false },
    ]);
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
