import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const push = vi.fn();
let searchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}));

vi.mock('@/lib/api', () => ({
  authApi: { register: vi.fn() },
}));

import { authApi } from '@/lib/api';
import RegisterPage from './page';

const register = vi.mocked(authApi.register);

beforeEach(() => {
  push.mockReset();
  register.mockReset();
  searchParams = new URLSearchParams();
});

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText('Username'), {
    target: { value: 'ada' },
  });
  fireEvent.change(screen.getByLabelText('Email'), {
    target: { value: 'ada@example.com' },
  });
  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: 'correct horse battery staple' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
}

describe('the register page', () => {
  it('announces a failed submit through a live region', async () => {
    // The banner used to be a plain <div>: a screen reader user submitted
    // the form, nothing was announced, and the page looked unchanged. The
    // alert role is what makes the failure reach them -- and it is also the
    // only thing a test can reliably grab it by.
    register.mockRejectedValue(new Error('A user with that name exists'));
    render(<RegisterPage />);

    fillAndSubmit();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('A user with that name exists');
    expect(push).not.toHaveBeenCalled();
  });

  it('shows nothing before a submit has failed', async () => {
    render(<RegisterPage />);
    await waitFor(() =>
      expect(screen.getByLabelText('Username')).toBeInTheDocument(),
    );

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('falls back to a generic message when the failure carries none', async () => {
    register.mockRejectedValue('not an Error');
    render(<RegisterPage />);

    fillAndSubmit();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Registration failed',
    );
  });

  it('sends the person to the dashboard on success', async () => {
    register.mockResolvedValue({
      user: { id: 1, username: 'ada', email: 'ada@example.com' },
    });
    render(<RegisterPage />);

    fillAndSubmit();

    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('honours a same-origin ?next=, so an invitation link resumes', async () => {
    searchParams = new URLSearchParams('next=/invite/abc123');
    register.mockResolvedValue({
      user: { id: 1, username: 'ada', email: 'ada@example.com' },
    });
    render(<RegisterPage />);

    fillAndSubmit();

    await waitFor(() => expect(push).toHaveBeenCalledWith('/invite/abc123'));
  });

  it('refuses an off-site ?next=, sending the person to the dashboard instead', async () => {
    // The open redirect this page is the entry point for: a ?next= a person
    // did not type themselves must never navigate off this origin.
    searchParams = new URLSearchParams('next=https://evil.com');
    register.mockResolvedValue({
      user: { id: 1, username: 'ada', email: 'ada@example.com' },
    });
    render(<RegisterPage />);

    fillAndSubmit();

    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'));
  });
});
