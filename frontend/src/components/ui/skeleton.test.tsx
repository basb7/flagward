import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Skeleton } from './skeleton';

describe('Skeleton', () => {
  it('renders a decorative block', () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it('merges an extra className with its own', () => {
    const { container } = render(<Skeleton className="h-4 w-24" />);
    const el = container.firstChild as HTMLElement;
    expect(el).toHaveClass('h-4');
    expect(el).toHaveClass('w-24');
    expect(el).toHaveClass('bg-muted');
  });

  it('is hidden from the accessibility tree', () => {
    const { container } = render(<Skeleton />);
    const el = container.firstChild as HTMLElement;
    expect(el).toHaveAttribute('aria-hidden', 'true');
  });

  it('exposes no accessible name of its own', () => {
    const { container } = render(<Skeleton />);
    const el = container.firstChild as HTMLElement;
    expect(el).not.toHaveAttribute('aria-label');
    expect(el).not.toHaveAttribute('role');
  });
});
