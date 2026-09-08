import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LOCALE,
  isLocale,
  LOCALE_LABELS,
  LOCALES,
} from '@/i18n/locales';

describe('isLocale', () => {
  it('accepts every locale the app ships', () => {
    for (const locale of LOCALES) {
      expect(isLocale(locale)).toBe(true);
    }
  });

  it('rejects language tags the app does not ship', () => {
    for (const value of ['fr', 'EN', '']) {
      expect(isLocale(value)).toBe(false);
    }
  });

  /**
   * This is the actual reason the guard exists: `request.ts` feeds this
   * value straight into a dynamic `import()`, so a value shaped like a
   * path traversal has to fail here, before it ever reaches that import.
   */
  it('rejects path-traversal-shaped values, so a crafted cookie cannot reach the dynamic import in request.ts', () => {
    for (const value of ['../../etc/passwd', 'en/../../secret']) {
      expect(isLocale(value)).toBe(false);
    }
  });
});

describe('DEFAULT_LOCALE', () => {
  it('is itself a supported locale', () => {
    expect(LOCALES).toContain(DEFAULT_LOCALE);
  });
});

describe('LOCALE_LABELS', () => {
  it('has exactly one label per supported locale, no more and no fewer', () => {
    expect(Object.keys(LOCALE_LABELS).sort()).toEqual([...LOCALES].sort());
  });
});
