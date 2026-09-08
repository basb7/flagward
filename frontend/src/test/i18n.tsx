import { type RenderOptions, render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import messages from '../../messages/en.json';

export { messages };

/**
 * Every component under test that calls `useTranslations` or `useLocale`
 * needs a provider above it -- outside a Server Component, next-intl has no
 * cookie to read the locale from, so tests supply the catalog directly
 * instead. English is enough here: coverage of the Spanish catalog itself is
 * `error-copy.test.ts`'s job, not each component test's.
 */
export function renderWithIntl(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
) {
  return render(ui, {
    wrapper: ({ children }) => (
      <NextIntlClientProvider locale="en" messages={messages}>
        {children}
      </NextIntlClientProvider>
    ),
    ...options,
  });
}
