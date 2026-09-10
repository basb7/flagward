import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithIntl } from '@/test/i18n';
import { LoadingRegion } from './loading-region';

describe('LoadingRegion', () => {
  it('announces itself as a status region with the translated name', () => {
    renderWithIntl(
      <LoadingRegion>
        <div>decorative content</div>
      </LoadingRegion>,
    );

    expect(
      screen.getByRole('status', { name: 'Loading content' }),
    ).toBeInTheDocument();
  });

  it('renders its children inside the region', () => {
    renderWithIntl(
      <LoadingRegion>
        <span>placeholder rows</span>
      </LoadingRegion>,
    );

    expect(screen.getByText('placeholder rows')).toBeInTheDocument();
  });

  it('announces what is loading when a label is given', () => {
    renderWithIntl(
      <LoadingRegion label="Loading organization members">
        <span>placeholder rows</span>
      </LoadingRegion>,
    );

    // Pages that show several regions at once need them told apart; without a
    // label they would all announce the same generic text.
    expect(
      screen.getByRole('status', { name: 'Loading organization members' }),
    ).toBeInTheDocument();
  });

  it('announces only the load, never the text of the placeholders it wraps', () => {
    renderWithIntl(
      <LoadingRegion>
        <span>revenue this month</span>
      </LoadingRegion>,
    );

    // An element with no `aria-label` takes its accessible name from its own
    // content. Drop the label and a screen reader stops announcing "loading"
    // and starts reading placeholder text as though it were real data, so the
    // wrapped text here is what makes that regression fail.
    expect(screen.getByRole('status')).toHaveAccessibleName('Loading content');
  });
});
