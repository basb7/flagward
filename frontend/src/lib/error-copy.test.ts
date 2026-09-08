import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { renderHook } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { createElement } from 'react';
import { describe, expect, it } from 'vitest';
import { LOCALES } from '@/i18n/locales';
import enMessages from '../../messages/en.json';
import esMessages from '../../messages/es.json';
import { useErrorCopy } from './error-copy';

const REPO_ROOT = resolve(process.cwd(), '..');
const SKIP = new Set([
  'node_modules',
  '.venv',
  '.git',
  'migrations',
  'tests',
  '.next',
  'frontend',
]);

const CATALOGS: Record<(typeof LOCALES)[number], typeof enMessages> = {
  en: enMessages,
  es: esMessages,
};

/** Every `{"error": "<code>"}` the backend can answer with. */
function backendErrorCodes(): Set<string> {
  const codes = new Set<string>();
  const pattern = /"error":\s*"([a-z_]+)"/g;

  const walk = (directory: string) => {
    for (const entry of readdirSync(directory)) {
      if (SKIP.has(entry) || entry.startsWith('.')) continue;

      const path = join(directory, entry);
      if (statSync(path).isDirectory()) {
        walk(path);
      } else if (entry.endsWith('.py')) {
        for (const match of readFileSync(path, 'utf8').matchAll(pattern)) {
          codes.add(match[1]);
        }
      }
    }
  };

  walk(REPO_ROOT);
  return codes;
}

/** Every key path in a nested object, e.g. `errors.token_expired`. */
function keyPaths(value: object, prefix = ''): string[] {
  return Object.entries(value).flatMap(([key, nested]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return nested && typeof nested === 'object'
      ? keyPaths(nested, path)
      : [path];
  });
}

describe('the error copy catalogs', () => {
  /**
   * The reason this file exists. An unmapped code still reaches the user --
   * as itself -- so nothing looks broken when copy is missing, and without
   * this test a new code ships unwritten and nobody notices until somebody
   * reads `project_limit_reached` in a dialog. Checked per locale: a code
   * translated in `en.json` but forgotten in `es.json` (or vice versa) is
   * exactly the gap this test exists to catch.
   */
  it('covers every error code the backend can answer with', () => {
    const codes = backendErrorCodes();

    expect(codes.size).toBeGreaterThan(0); // the walk found the backend at all

    for (const locale of LOCALES) {
      const known = Object.keys(CATALOGS[locale].errors);
      const missing = [...codes].filter((code) => !known.includes(code)).sort();
      expect(
        missing,
        `${locale}.json is missing: ${missing.join(', ')}`,
      ).toEqual([]);
    }
  });

  it('has no copy for codes the backend cannot send', () => {
    const codes = backendErrorCodes();

    for (const locale of LOCALES) {
      const stale = Object.keys(CATALOGS[locale].errors)
        .filter((code) => !codes.has(code))
        .sort();
      expect(
        stale,
        `${locale}.json has stale codes: ${stale.join(', ')}`,
      ).toEqual([]);
    }
  });

  /**
   * Stops `es.json` from silently drifting behind `en.json` -- a namespace
   * or key added to one catalog and forgotten in the other would otherwise
   * only surface as a missing string in production, in whichever locale
   * wasn't updated.
   */
  it('have exactly the same keys across every namespace', () => {
    const [first, ...rest] = LOCALES;
    const referenceKeys = keyPaths(CATALOGS[first]).sort();

    for (const locale of rest) {
      const keys = keyPaths(CATALOGS[locale]).sort();
      expect(keys, `${locale}.json's keys differ from ${first}.json's`).toEqual(
        referenceKeys,
      );
    }
  });
});

// This file stays `.ts`, not `.tsx`, so the wrapper is built with
// `createElement` rather than JSX syntax a plain `.ts` file can't parse.
function renderErrorCopy() {
  return renderHook(() => useErrorCopy(), {
    wrapper: ({ children }) =>
      createElement(NextIntlClientProvider, {
        locale: 'en',
        messages: enMessages,
        children,
      }),
  });
}

describe('useErrorCopy', () => {
  it('translates a code it knows', () => {
    const { result } = renderErrorCopy();
    expect(result.current('invitation_expired')).toBe(
      'This invitation has expired.',
    );
  });

  it('returns an unknown code as itself, so it stays traceable', () => {
    const { result } = renderErrorCopy();
    expect(result.current('something_new')).toBe('something_new');
  });

  it('prefers a caller fallback for an unknown code', () => {
    const { result } = renderErrorCopy();
    expect(result.current('something_new', 'This link is not valid.')).toBe(
      'This link is not valid.',
    );
  });

  /**
   * The `useCallback` inside the hook is what makes this hold. Without it the
   * hook hands back a new function on every render. That is invisible today --
   * every call site uses it inside a plain event handler -- and turns into a
   * hazard the moment one is referenced from a `useCallback`, `useEffect`, or
   * `useMemo` body: a changing identity either gets quietly omitted from the
   * dependency array, or re-runs the effect on every single render.
   */
  it('returns a stable function identity across re-renders', () => {
    const { result, rerender } = renderErrorCopy();
    const first = result.current;

    rerender();

    expect(result.current).toBe(first);
  });

  it('ignores the fallback when it knows the code', () => {
    const { result } = renderErrorCopy();
    expect(
      result.current('invitation_expired', 'This link is not valid.'),
    ).toBe('This invitation has expired.');
  });
});
