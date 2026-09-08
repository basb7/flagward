import { describe, expect, it, vi } from 'vitest';

const set = vi.fn();

vi.mock('next/headers', () => ({
  cookies: () => Promise.resolve({ set }),
}));

import { changeLocaleAction } from '@/i18n/actions';

describe('changeLocaleAction', () => {
  it('writes the locale cookie with a supported locale', async () => {
    await changeLocaleAction('es');

    expect(set).toHaveBeenCalledWith('locale', 'es', expect.any(Object));
  });

  /**
   * `isLocale` guards this boundary too, not just `request.ts`'s read side --
   * a server action is still a network-reachable entry point, so an
   * unsupported value must write nothing rather than reach the cookie jar.
   */
  it('writes nothing for an unsupported locale', async () => {
    // @ts-expect-error -- deliberately calling with a value outside `Locale`
    await changeLocaleAction('fr');

    expect(set).not.toHaveBeenCalled();
  });

  /**
   * Without an explicit lifetime the browser treats this as a session
   * cookie and drops it on close, so somebody who picks Spanish today is
   * back to English tomorrow. There is no user-profile field behind this
   * preference -- the cookie's lifetime *is* the feature's memory, which is
   * why a missing `maxAge` reads to a person as the switch not working.
   */
  it('persists the choice past the browser session', async () => {
    await changeLocaleAction('es');

    const options = set.mock.calls.at(-1)?.[2];
    expect(options?.maxAge).toBeGreaterThan(60 * 60 * 24 * 30);
  });

  /**
   * Nothing client-side reads this cookie -- `useLocale()` takes the locale
   * from the server-rendered intl provider -- so `httpOnly` costs nothing
   * and puts it out of reach of any script on the page.
   */
  it('keeps the cookie out of reach of client scripts', async () => {
    await changeLocaleAction('en');

    const options = set.mock.calls.at(-1)?.[2];
    expect(options?.httpOnly).toBe(true);
    expect(options?.sameSite).toBe('lax');
    expect(options?.path).toBe('/');
  });

  /**
   * `request.ts` reads this exact cookie name back out. A rename on either
   * side would silently stop locale changes from taking effect, with
   * nothing to fail loudly -- this pins the name both sides agree on.
   */
  it('names the cookie exactly "locale"', async () => {
    await changeLocaleAction('en');

    expect(set.mock.calls.at(-1)?.[0]).toBe('locale');
  });
});
