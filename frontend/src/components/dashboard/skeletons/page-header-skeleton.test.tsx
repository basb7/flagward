import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PageHeaderSkeleton } from './page-header-skeleton';

describe('PageHeaderSkeleton', () => {
  it('renders a title placeholder and a description placeholder', () => {
    const { container } = render(<PageHeaderSkeleton />);
    expect(
      container.querySelector('[data-slot="page-header-title-skeleton"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelector('[data-slot="page-header-description-skeleton"]'),
    ).toBeInTheDocument();
  });

  it('omits the back-button placeholder by default', () => {
    const { container } = render(<PageHeaderSkeleton />);
    expect(
      container.querySelector('[data-slot="page-header-back-skeleton"]'),
    ).not.toBeInTheDocument();
  });

  it('renders a back-button placeholder when asked', () => {
    const { container } = render(<PageHeaderSkeleton withBackButton />);
    expect(
      container.querySelector('[data-slot="page-header-back-skeleton"]'),
    ).toBeInTheDocument();
  });
});
