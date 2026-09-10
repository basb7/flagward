import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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

// Never resolve, so the page's `isLoading` state stays true for the test.
vi.mock('@/lib/api', () => ({
  flagsApi: { list: vi.fn(() => new Promise(() => {})) },
  environmentsApi: { list: vi.fn(() => new Promise(() => {})) },
}));

describe('FlagsPage loading state', () => {
  it('renders the announcing skeleton region instead of the spinner while flags load', () => {
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
