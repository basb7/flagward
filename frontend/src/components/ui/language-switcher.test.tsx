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
 * The menu primitives are stood in for, and the reason is measured rather
 * than assumed: mounting the real Base UI dropdown under jsdom costs about a
 * second the first time and climbs to roughly six by the fourth mount in the
 * same file -- six identical trivial tests measured 1.3s, 3.1s, 4.8s, 5.8s,
 * 5.8s, 5.9s. Something each mount leaves behind is paid for by the next
 * test. Six real mounts took 140s on CI, past the point where Vitest's worker
 * reporter gives up, and the whole file failed while every assertion in it
 * passed.
 *
 * So these tests exercise this component's own logic -- the async transition,
 * the catch, the toast, and the fact that the checkmark follows the locale
 * rather than the click. What they deliberately do NOT prove is that Base
 * UI's radio group actually calls `onValueChange`; that is exactly one test,
 * against the real primitives, in `language-switcher.wiring.test.tsx`. Adding
 * a behaviour test here is free; adding one there is not.
 *
 * The stand-ins use `createElement` because a `vi.mock` factory is hoisted
 * above the imports and cannot reach the JSX runtime at the top of the file.
 */
vi.mock('@/components/ui/dropdown-menu', async () => {
  const { createContext, createElement, cloneElement, useContext } =
    await import('react');

  const RadioContext = createContext<{
    value?: string;
    onValueChange?: (value: string) => void;
  }>({});

  return {
    DropdownMenu: ({ children }: { children?: React.ReactNode }) =>
      createElement('div', null, children),

    // The real trigger takes Base UI's `render` prop -- an element to clone
    // and merge props into -- so cloning it here keeps the Button's
    // `aria-label` and `disabled`, which two of these tests assert on.
    DropdownMenuTrigger: ({
      render,
      children,
    }: {
      render: React.ReactElement;
      children?: React.ReactNode;
    }) => cloneElement(render, {}, children),

    DropdownMenuContent: ({ children }: { children?: React.ReactNode }) =>
      createElement('div', null, children),

    DropdownMenuRadioGroup: ({
      value,
      onValueChange,
      children,
    }: {
      value?: string;
      onValueChange?: (value: string) => void;
      children?: React.ReactNode;
    }) =>
      createElement(
        RadioContext.Provider,
        { value: { value, onValueChange } },
        children,
      ),

    DropdownMenuRadioItem: ({
      value,
      children,
    }: {
      value: string;
      children?: React.ReactNode;
    }) => {
      const group = useContext(RadioContext);
      return createElement(
        'button',
        {
          type: 'button',
          role: 'menuitemradio',
          'aria-checked': group.value === value ? 'true' : 'false',
          onClick: () => group.onValueChange?.(value),
        },
        children,
      );
    },
  };
});

/** With the primitives stood in for, the items are always in the document. */
function item(label: string) {
  return screen.getByRole('menuitemradio', { name: label });
}

describe('LanguageSwitcher', () => {
  const changeLocaleAction = vi.fn<(locale: 'en' | 'es') => Promise<void>>();

  beforeEach(() => {
    changeLocaleAction.mockReset().mockResolvedValue();
    success.mockReset();
    showError.mockReset();
  });

  it('renders both languages and marks the current one', () => {
    renderWithIntl(
      <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
    );

    expect(item(LOCALE_LABELS.en)).toHaveAttribute('aria-checked', 'true');
    expect(item(LOCALE_LABELS.es)).toHaveAttribute('aria-checked', 'false');
  });

  it('invokes the action with the chosen locale', () => {
    renderWithIntl(
      <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
    );

    fireEvent.click(item(LOCALE_LABELS.es));

    expect(changeLocaleAction).toHaveBeenCalledWith('es');
  });

  /**
   * `onValueChange` used to `void` this promise, which discarded a rejected
   * cookie write outright: nobody was ever told the switch did not take. This
   * is the regression test for that swallowed rejection.
   */
  it('shows an error toast when the action rejects', async () => {
    changeLocaleAction.mockRejectedValue(new Error('network down'));
    renderWithIntl(
      <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
    );

    fireEvent.click(item(LOCALE_LABELS.es));
    // Awaiting the mock's own settled promise flushes the microtask queue up
    // to and past the component's `catch`.
    await changeLocaleAction.mock.results[0]?.value.catch(() => {});

    expect(showError).toHaveBeenCalledTimes(1);
  });

  /**
   * `value={locale}` is controlled by the locale the server rendered, so a
   * failed switch has to leave the selection where it was. If the group
   * tracked the click instead, the menu would go on claiming a language the
   * cookie never took -- an error toast beside a checkmark contradicting it.
   */
  it('leaves the selection on the real locale when the action rejects', async () => {
    changeLocaleAction.mockRejectedValue(new Error('network down'));
    renderWithIntl(
      <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
    );

    fireEvent.click(item(LOCALE_LABELS.es));
    await changeLocaleAction.mock.results[0]?.value.catch(() => {});

    expect(item(LOCALE_LABELS.en)).toHaveAttribute('aria-checked', 'true');
    expect(item(LOCALE_LABELS.es)).toHaveAttribute('aria-checked', 'false');
  });

  it('shows no error toast when the action succeeds', async () => {
    renderWithIntl(
      <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
    );

    fireEvent.click(item(LOCALE_LABELS.es));
    await changeLocaleAction.mock.results[0]?.value;

    // Anchored on a positive assertion first. On its own,
    // `not.toHaveBeenCalled` cannot tell "the switch succeeded quietly" apart
    // from "the switch never ran": a refactor that stopped calling the action
    // would leave `showError` untouched and this test green over a dead
    // control.
    expect(changeLocaleAction).toHaveBeenCalledWith('es');
    expect(showError).not.toHaveBeenCalled();
  });

  it('has an accessible, keyboard-reachable trigger', () => {
    renderWithIntl(
      <LanguageSwitcher changeLocaleAction={changeLocaleAction} />,
    );

    const trigger = screen.getByRole('button', { name: 'Language' });
    expect(trigger).toHaveAccessibleName('Language');
    expect(trigger).not.toHaveAttribute('disabled');
    expect(trigger.tagName).toBe('BUTTON');
  });
});
