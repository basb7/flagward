import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LOCALE_LABELS } from '@/i18n/locales';
import { renderWithIntl } from '@/test/i18n';
import { LanguageSwitcher } from './language-switcher';

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

/**
 * The one test that mounts the real Base UI dropdown.
 *
 * `language-switcher.test.tsx` stands the menu primitives in for fast
 * stand-ins, which is what keeps that file's six tests off the ~6s-per-mount
 * cost this component carries under jsdom. The gap that leaves is precisely
 * this: nothing there proves Base UI's radio group calls `onValueChange` at
 * all, so a stand-in that quietly stopped matching the real API would take
 * every one of those tests with it and none would fail.
 *
 * This file closes that gap and deliberately holds a single test. Its cost is
 * one mount; a second test in here would cost three seconds more than the
 * first, and a fourth about six. Behaviour belongs in the fast file.
 *
 * It also stays deliberately shallow -- click the item, assert the action
 * received the locale. Anything about what happens after the action settles is
 * this component's logic, not the primitives' wiring, and has a cheaper home.
 */
describe('LanguageSwitcher, against the real menu primitives', () => {
  it('reaches the action when a language is picked from the open menu', () => {
    const changeLocaleAction = vi
      .fn<(locale: 'en' | 'es') => Promise<void>>()
      .mockResolvedValue();

    renderWithIntl(
      <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
    );

    // Base UI's menu opens synchronously here -- there is no animation to wait
    // out under jsdom -- so the item is queryable right after the click.
    // `waitFor` is deliberately not used: it pairs a MutationObserver with
    // Base UI's own positioning updates and never settles in this
    // environment, hanging the test until it times out.
    fireEvent.click(screen.getByRole('button', { name: 'Language' }));
    fireEvent.click(
      screen.getByRole('menuitemradio', { name: LOCALE_LABELS.es }),
    );

    expect(changeLocaleAction).toHaveBeenCalledWith('es');
  });
});
