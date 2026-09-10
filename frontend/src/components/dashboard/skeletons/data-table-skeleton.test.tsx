import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DataTableSkeleton } from './data-table-skeleton';

describe('DataTableSkeleton', () => {
  it('renders the requested number of header columns', () => {
    render(<DataTableSkeleton columns={4} rows={2} />);
    const headRow = screen.getAllByRole('row')[0];
    expect(headRow?.querySelectorAll('[data-slot="table-head"]')).toHaveLength(
      4,
    );
  });

  it('renders the requested number of body rows', () => {
    render(<DataTableSkeleton columns={4} rows={3} />);
    // One header row plus `rows` body rows.
    expect(screen.getAllByRole('row')).toHaveLength(4);
  });

  it('falls back to five body rows when no row count is given', () => {
    render(<DataTableSkeleton columns={3} />);
    // Pinned, not `toBeGreaterThan(1)`: that would still pass if the default
    // silently dropped to a single row, which is the regression this guards.
    expect(screen.getAllByRole('row')).toHaveLength(6);
  });

  it('gives every body cell a decorative placeholder', () => {
    const { container } = render(<DataTableSkeleton columns={2} rows={1} />);
    const bodyCells = container.querySelectorAll('[data-slot="table-cell"]');
    expect(bodyCells).toHaveLength(2);
    for (const cell of bodyCells) {
      expect(cell.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
    }
  });
});
