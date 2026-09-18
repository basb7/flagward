import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithIntl } from '@/test/i18n';
import RulesPage from './page';

// Mirrors the pattern in `environments/page.test.tsx`: mock the context
// hooks directly rather than mounting the real providers, so this test only
// pays for `RulesPage`'s own render logic.
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'flag-1' }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

// Never resolve, so the page's `isLoading` state stays true for the test.
vi.mock('@/lib/api', () => ({
  flagsApi: { get: vi.fn(() => new Promise(() => {})) },
  rulesApi: { list: vi.fn(() => new Promise(() => {})), create: vi.fn() },
  conditionsApi: {},
  variantsApi: { replaceSet: vi.fn() },
}));

// Variant sliders mirror the manual percentage inputs, so display-value
// queries match twice -- this scopes them to the number inputs.
function numberInputWithValue(value: string) {
  const matches = screen
    .getAllByDisplayValue(value)
    .filter((el) => (el as HTMLInputElement).type === 'number');
  expect(matches).toHaveLength(1);
  return matches[0];
}

describe('RulesPage loading state', () => {
  it('renders the announcing skeleton region instead of the spinner while rule data loads', () => {
    renderWithIntl(<RulesPage />);

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Strategy Rules' }),
    ).toBeInTheDocument();
  });
});

const booleanFlag = {
  id: 'flag-1',
  environment: 'env-1',
  key: 'my-flag',
  name: 'My Flag',
  description: '',
  is_enabled: true,
  effective_is_enabled: true,
  active_override: null,
  flag_type: 'BOOLEAN' as const,
  rules: [],
  variants: [],
};

const multivariateFlag = {
  ...booleanFlag,
  flag_type: 'MULTIVARIATE' as const,
  variants: [
    {
      id: 'variant-1',
      flag: 'flag-1',
      name: 'control',
      percentage_allocation: 60,
      is_control: true,
    },
    {
      id: 'variant-2',
      flag: 'flag-1',
      name: 'treatment',
      percentage_allocation: 40,
      is_control: false,
    },
  ],
};

const sampleRule = {
  id: 'rule-1',
  priority: 5,
  operator_logic: 'OR' as const,
  rollout_variant: 'variant-2',
  rollout_percentage: 100,
  conditions: [],
};

describe('RulesPage variant breakdown', () => {
  it('renders the variant percentage breakdown for a MULTIVARIATE flag', async () => {
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: vi.fn(),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Variant Breakdown')).toBeInTheDocument(),
    );
    expect(screen.getByText('control')).toBeInTheDocument();
    expect(screen.getByText('treatment')).toBeInTheDocument();
    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(screen.getByText('40%')).toBeInTheDocument();
    expect(screen.getByText('Control (default)')).toBeInTheDocument();

    vi.doUnmock('@/lib/api');
  });

  it('does not render the variant breakdown for a BOOLEAN flag', async () => {
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(booleanFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: vi.fn(),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Strategy Rules' }),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText('Variant Breakdown')).not.toBeInTheDocument();

    vi.doUnmock('@/lib/api');
  });
});

describe('RulesPage create rule dialog rollout', () => {
  it('shows the rollout variant select only for a MULTIVARIATE flag', async () => {
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: vi.fn(() => Promise.resolve({})),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('New Rule')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('New Rule'));

    expect(await screen.findByLabelText('Rollout Variant')).toBeInTheDocument();

    vi.doUnmock('@/lib/api');
  });

  it('does not show the rollout variant select for a BOOLEAN flag', async () => {
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(booleanFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: vi.fn(() => Promise.resolve({})),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('New Rule')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('New Rule'));

    await waitFor(() =>
      expect(
        screen.getByText('Add a new targeting rule for this flag.'),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByLabelText('Rollout Variant')).not.toBeInTheDocument();

    vi.doUnmock('@/lib/api');
  });

  it('sends rollout_variant and rollout_percentage in the create call when a variant is selected', async () => {
    const createSpy = vi.fn(() => Promise.resolve({}));
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: createSpy,
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('New Rule')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('New Rule'));

    const select = await screen.findByLabelText('Rollout Variant');
    fireEvent.change(select, { target: { value: 'variant-2' } });

    // Base UI's slider thumb is hidden from the accessibility tree, so the
    // native range input is queried directly instead of `role="slider"`.
    const slider = document.body.querySelector('input[type="range"]');
    expect(slider).not.toBeNull();
    if (slider) fireEvent.change(slider, { target: { value: '98' } });

    fireEvent.click(screen.getByText('Create'));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          rollout_variant: 'variant-2',
          rollout_percentage: 98,
        }),
      ),
    );

    vi.doUnmock('@/lib/api');
  });
});

describe('RulesPage variant editing', () => {
  it('enters edit mode with the current variants prefilled', async () => {
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: vi.fn(),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Variant Breakdown')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    expect(screen.getByDisplayValue('control')).toBeInTheDocument();
    expect(screen.getByDisplayValue('treatment')).toBeInTheDocument();
    // The control percentage is derived, shown as read-only text.
    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(numberInputWithValue('40')).toBeInTheDocument();

    vi.doUnmock('@/lib/api');
  });

  it('moving a variant slider updates its manual percentage input', async () => {
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: vi.fn(),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Variant Breakdown')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    // Same hidden-thumb pattern as the rollout slider: query the range input.
    // The control variant has no slider (its percentage is derived), so the
    // only one rendered here is the editable treatment slider.
    const sliders = document.body.querySelectorAll('input[type="range"]');
    expect(sliders.length).toBeGreaterThan(0);
    fireEvent.change(sliders[0], { target: { value: '30' } });

    expect(numberInputWithValue('30')).toBeInTheDocument();

    vi.doUnmock('@/lib/api');
  });

  it('recalculates the control percentage automatically and never blocks saving', async () => {
    const replaceSetSpy = vi.fn(() => Promise.resolve([]));
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: vi.fn(),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: replaceSetSpy },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Variant Breakdown')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    fireEvent.change(numberInputWithValue('40'), {
      target: { value: '30' },
    });

    expect(screen.getByText('70%')).toBeInTheDocument();
    expect(screen.queryByText(/must sum to 100/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(replaceSetSpy).toHaveBeenCalledTimes(1));

    vi.doUnmock('@/lib/api');
  });

  it('saves a rebalanced set via replaceSet with every existing variant id', async () => {
    const replaceSetSpy = vi.fn(() => Promise.resolve([]));
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [] })),
        create: vi.fn(),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: replaceSetSpy },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Variant Breakdown')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

    fireEvent.change(numberInputWithValue('40'), {
      target: { value: '30' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(replaceSetSpy).toHaveBeenCalledWith('flag-1', [
        {
          id: 'variant-1',
          name: 'control',
          percentage_allocation: 70,
          is_control: true,
        },
        {
          id: 'variant-2',
          name: 'treatment',
          percentage_allocation: 30,
          is_control: false,
        },
      ]),
    );

    vi.doUnmock('@/lib/api');
  });
});

describe('RulesPage rule editing', () => {
  it('opens the edit dialog prefilled with the rule current values', async () => {
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [sampleRule] })),
        create: vi.fn(),
        update: vi.fn(),
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Rule #5')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit Rule #5' }));

    expect(await screen.findByText('Edit Strategy Rule')).toBeInTheDocument();
    expect(screen.getByDisplayValue('5')).toBeInTheDocument();
    expect(
      (screen.getByLabelText('Rollout Variant') as HTMLSelectElement).value,
    ).toBe('variant-2');

    vi.doUnmock('@/lib/api');
  });

  it('saves edits via rulesApi.update instead of create', async () => {
    const updateSpy = vi.fn(() => Promise.resolve({}));
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(multivariateFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [sampleRule] })),
        create: vi.fn(),
        update: updateSpy,
      },
      conditionsApi: {},
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Rule #5')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit Rule #5' }));

    const prioritySelect = await screen.findByDisplayValue('5');
    fireEvent.change(prioritySelect, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() =>
      expect(updateSpy).toHaveBeenCalledWith('rule-1', {
        priority: 2,
        operator_logic: 'OR',
        rollout_variant: 'variant-2',
        rollout_percentage: 100,
      }),
    );

    vi.doUnmock('@/lib/api');
  });
});

describe('RulesPage percentage split condition', () => {
  it('shows a single slider instead of the attribute and value inputs', async () => {
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(booleanFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [sampleRule] })),
        create: vi.fn(),
      },
      conditionsApi: { create: vi.fn(() => Promise.resolve({})) },
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Rule #5')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('Condition'));

    const operatorSelect = await screen.findByLabelText('Operator');
    fireEvent.change(operatorSelect, {
      target: { value: 'PERCENTAGE_SPLIT' },
    });

    await waitFor(() =>
      expect(screen.getByText('Percentage Split')).toBeInTheDocument(),
    );
    // No trait needed: the attribute field hides, the slider takes over.
    expect(screen.queryByLabelText('Attribute')).not.toBeInTheDocument();
    expect(document.body.querySelector('input[type="range"]')).not.toBeNull();

    vi.doUnmock('@/lib/api');
  });

  it('sends the wrapped percentage value with the user_id convention', async () => {
    const createSpy = vi.fn(() => Promise.resolve({}));
    vi.resetModules();
    vi.doMock('@/lib/api', () => ({
      flagsApi: { get: vi.fn(() => Promise.resolve(booleanFlag)) },
      rulesApi: {
        list: vi.fn(() => Promise.resolve({ results: [sampleRule] })),
        create: vi.fn(),
      },
      conditionsApi: { create: createSpy },
      variantsApi: { replaceSet: vi.fn() },
    }));
    const { default: RulesPageWithData } = await import('./page');
    renderWithIntl(<RulesPageWithData />);

    await waitFor(() =>
      expect(screen.getByText('Rule #5')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText('Condition'));

    const operatorSelect = await screen.findByLabelText('Operator');
    fireEvent.change(operatorSelect, {
      target: { value: 'PERCENTAGE_SPLIT' },
    });

    await waitFor(() =>
      expect(document.body.querySelector('input[type="range"]')).not.toBeNull(),
    );
    const slider = document.body.querySelector('input[type="range"]');
    if (slider) fireEvent.change(slider, { target: { value: '60' } });

    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          rule: 'rule-1',
          attribute: 'user_id',
          operator: 'PERCENTAGE_SPLIT',
          value: { value: 60 },
        }),
      ),
    );

    vi.doUnmock('@/lib/api');
  });
});
