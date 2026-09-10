import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatCardsSkeleton } from './stat-cards-skeleton';

describe('StatCardsSkeleton', () => {
  it('renders exactly the requested number of stat card placeholders', () => {
    const { container } = render(<StatCardsSkeleton count={4} />);
    expect(
      container.querySelectorAll('[data-slot="stat-card-skeleton"]'),
    ).toHaveLength(4);
  });

  it('renders a different count when asked', () => {
    const { container } = render(<StatCardsSkeleton count={3} />);
    expect(
      container.querySelectorAll('[data-slot="stat-card-skeleton"]'),
    ).toHaveLength(3);
  });

  it('merges an extra className onto the grid wrapper', () => {
    const { container } = render(
      <StatCardsSkeleton count={2} className="sm:grid-cols-3" />,
    );
    expect(container.firstChild).toHaveClass('sm:grid-cols-3');
  });
});
