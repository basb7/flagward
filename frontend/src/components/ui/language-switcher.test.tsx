import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LOCALE_LABELS } from '@/i18n/locales';
import { renderWithIntl } from '@/test/i18n';
import { LanguageSwitcher } from './language-switcher';

const success = vi.fn();
const showError = vi.fn();

// Same pattern as create-dialogs.test.tsx: mock the hook rather than wrap
// every render in a real `ToastProvider`, so this component's tests are the
// only ones that pay for mounting sonner's `<Toaster />`.
vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success, error: showError, info: vi.fn() }),
}));

/**
 * Opening this menu is expensive under jsdom -- Base UI does real positioning
 * work -- and every test below opens it at least once. On a fast machine each
 * one lands just inside Vitest's 5s default; on CI's slower runner three of
 * them timed out. The budget is declared here rather than raised globally,
 * because 5s is the right default for every other test in the suite.
 */
const MENU_TIMEOUT = 30_000;

// Base UI's menu opens synchronously here -- there is no animation to wait
// out under jsdom (`data-instant="click"`) -- so the item is queryable right
// after the click. `waitFor` is deliberately not used: it pairs a
// MutationObserver with Base UI's own positioning updates and never settles
// in this environment, hanging the test until it times out.
function openMenu() {
  fireEvent.click(screen.getByRole('button', { name: 'Language' }));
}

describe('LanguageSwitcher', () => {
  const changeLocaleAction = vi.fn<(locale: 'en' | 'es') => Promise<void>>();

  beforeEach(() => {
    changeLocaleAction.mockReset().mockResolvedValue();
    success.mockReset();
    showError.mockReset();
  });

  it(
    'renders both languages and marks the current one',
    () => {
      renderWithIntl(
        <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
      );
      openMenu();

      const current = screen.getByRole('menuitemradio', {
        name: LOCALE_LABELS.en,
      });
      const other = screen.getByRole('menuitemradio', {
        name: LOCALE_LABELS.es,
      });
      expect(current).toHaveAttribute('aria-checked', 'true');
      expect(other).toHaveAttribute('aria-checked', 'false');
    },
    MENU_TIMEOUT,
  );

  it(
    'invokes the action with the chosen locale',
    () => {
      renderWithIntl(
        <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
      );
      openMenu();

      fireEvent.click(
        screen.getByRole('menuitemradio', { name: LOCALE_LABELS.es }),
      );

      expect(changeLocaleAction).toHaveBeenCalledWith('es');
    },
    MENU_TIMEOUT,
  );

  /**
   * `onValueChange` used to `void` this promise. The radio group had already
   * moved visually by the time a rejected cookie write surfaced, and nobody
   * was ever told the switch did not take -- this is the regression test for
   * that swallowed rejection.
   */
  it(
    'shows an error toast when the action rejects',
    async () => {
      changeLocaleAction.mockRejectedValue(new Error('network down'));
      renderWithIntl(
        <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
      );
      openMenu();

      fireEvent.click(
        screen.getByRole('menuitemradio', { name: LOCALE_LABELS.es }),
      );

      // Awaiting the mock's own settled promise, rather than polling with
      // `waitFor` (its interval never gets a turn here -- see `openMenu`),
      // flushes the microtask queue up to and past the component's `catch`.
      await changeLocaleAction.mock.results[0]?.value.catch(() => {});

      expect(showError).toHaveBeenCalledTimes(1);
    },
    MENU_TIMEOUT,
  );

  /**
   * `value={locale}` is controlled by the locale the server rendered, so a
   * failed switch has to leave the selection where it was. If the group
   * tracked the click instead, the menu would go on claiming a language the
   * cookie never took -- an error toast plus a checkmark that contradicts it.
   */
  it(
    'leaves the selection on the real locale when the action rejects',
    async () => {
      changeLocaleAction.mockRejectedValue(new Error('network down'));
      renderWithIntl(
        <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
      );
      openMenu();

      fireEvent.click(
        screen.getByRole('menuitemradio', { name: LOCALE_LABELS.es }),
      );
      await changeLocaleAction.mock.results[0]?.value.catch(() => {});

      openMenu();
      expect(
        screen.getByRole('menuitemradio', { name: LOCALE_LABELS.en }),
      ).toHaveAttribute('aria-checked', 'true');
      expect(
        screen.getByRole('menuitemradio', { name: LOCALE_LABELS.es }),
      ).toHaveAttribute('aria-checked', 'false');
    },
    MENU_TIMEOUT,
  );

  it(
    'shows no error toast when the action succeeds',
    async () => {
      renderWithIntl(
        <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
      );
      openMenu();

      fireEvent.click(
        screen.getByRole('menuitemradio', { name: LOCALE_LABELS.es }),
      );

      await changeLocaleAction.mock.results[0]?.value;

      // Anchored on a positive assertion first. On its own, `not.toHaveBeenCalled`
      // cannot tell "the switch succeeded quietly" apart from "the switch never
      // ran": a refactor that stopped calling the action would leave `showError`
      // untouched and this test green over a dead control.
      expect(changeLocaleAction).toHaveBeenCalledWith('es');
      expect(showError).not.toHaveBeenCalled();
    },
    MENU_TIMEOUT,
  );

  it(
    'has an accessible, keyboard-reachable trigger',
    () => {
      renderWithIntl(
        <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
      );

      const trigger = screen.getByRole('button', { name: 'Language' });
      expect(trigger).toHaveAccessibleName('Language');
      expect(trigger).not.toHaveAttribute('disabled');
      expect(trigger.tagName).toBe('BUTTON');
    },
    MENU_TIMEOUT,
  );
});
