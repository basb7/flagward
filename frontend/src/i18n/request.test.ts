import { describe, expect, it, vi } from 'vitest';

import { DEFAULT_LOCALE } from '@/i18n/locales';
import enMessages from '../../messages/en.json';
import esMessages from '../../messages/es.json';

const get = vi.fn();

vi.mock('next/headers', () => ({
  cookies: () => Promise.resolve({ get }),
}));

/**
 * Vitest resolves `next-intl/server` to the package's react-client build,
 * whose `getRequestConfig` throws "not supported in Client Components". The
 * react-server build -- the one Next actually loads for this module -- is the
 * identity function, verbatim:
 *
 *   function getRequestConfig(createRequestConfig) { return createRequestConfig; }
 *
 * (`node_modules/next-intl/dist/esm/production/server/react-server/`.) So this
 * is not a stand-in for the real behaviour, it *is* the real behaviour; the
 * mock only sidesteps a resolution condition Vitest has no reason to set.
 */
vi.mock('next-intl/server', () => ({
  getRequestConfig: (createRequestConfig: unknown) => createRequestConfig,
}));

import requestConfig from '@/i18n/request';

/**
 * With `getRequestConfig` as the identity function, the module's default
 * export *is* the resolver. The cast only drops the parameter next-intl
 * declares and this resolver ignores.
 */
const resolve = requestConfig as unknown as () => Promise<{
  locale: string;
  messages: typeof enMessages;
}>;

function withCookie(value: string | undefined) {
  get.mockReset();
  get.mockReturnValue(value === undefined ? undefined : { value });
}

describe('the request config', () => {
  it('serves the default locale when nobody has chosen one', async () => {
    withCookie(undefined);

    const config = await resolve();

    expect(config.locale).toBe(DEFAULT_LOCALE);
    expect(config.messages).toEqual(enMessages);
  });

  /**
   * The whole point of the cookie: a chosen locale has to come back as that
   * locale's catalog, not just as a string nothing reads.
   */
  it('serves the catalog for the locale in the cookie', async () => {
    withCookie('es');

    const config = await resolve();

    expect(config.locale).toBe('es');
    expect(config.messages).toEqual(esMessages);
  });

  it('falls back to the default for a language it does not ship', async () => {
    withCookie('fr');

    const config = await resolve();

    expect(config.locale).toBe(DEFAULT_LOCALE);
    expect(config.messages).toEqual(enMessages);
  });

  /**
   * This is the reason `isLocale` guards the read at all. The cookie value
   * feeds a dynamic `import()` of `messages/${locale}.json`, so a crafted
   * value is a request to import an arbitrary path. `locales.test.ts` proves
   * the guard rejects these shapes; this proves the guard is actually wired
   * into the resolution rather than merely present in the codebase.
   */
  it.each(['../../etc/passwd', 'en/../../secret', '../package'])(
    'refuses to resolve a traversal-shaped cookie (%s)',
    async (crafted) => {
      withCookie(crafted);

      const config = await resolve();

      expect(config.locale).toBe(DEFAULT_LOCALE);
      expect(config.messages).toEqual(enMessages);
    },
  );
});
