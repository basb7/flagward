import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithIntl } from '@/test/i18n';
import DashboardLayout from './layout';

// `DashboardContent` (the component that owns the loading branch) is not
// exported -- only the default-exported `DashboardLayout`, which wraps it in
// `AuthProvider`/`TenantProvider`, is. Rather than mounting the real
// providers, both modules are mocked: `AuthProvider`/`TenantProvider` become
// pass-through wrappers, and `useAuth` drives the loading branch directly.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/lib/auth-context', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({ user: null, isLoading: true }),
}));

vi.mock('@/lib/tenant-context', () => ({
  TenantProvider: ({ children }: { children: React.ReactNode }) => children,
}));

describe('DashboardLayout loading state', () => {
  it('renders the announcing skeleton region instead of the spinner while auth resolves', () => {
    renderWithIntl(
      <DashboardLayout>
        <div>content</div>
      </DashboardLayout>,
    );

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('img', { name: 'Loading' }),
    ).not.toBeInTheDocument();
  });
});
