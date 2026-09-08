/**
 * The single source of truth for which locales this app ships. Everything
 * that needs to enumerate, validate, or label a locale -- the cookie guard in
 * `request.ts`, the message-coverage test, the language switcher -- reads
 * from here, so adding a language is a one-line change in one file instead
 * of a hunt through every place a locale list was copied.
 */
export const LOCALES = ['en', 'es'] as const;

export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'en';

/** Narrows an arbitrary string -- e.g. a cookie value -- to a supported `Locale`. */
export function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
}

/**
 * Each language's own name for itself, not its English translation -- a
 * person scanning a language switcher for their language reads it in that
 * language, not in whichever one the app happens to be in right now.
 */
export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'English',
  es: 'Español',
};

/**
 * The cookie `request.ts` reads and `actions.ts` writes. Both sides naming
 * it from here is what stops a rename on one side from silently ending
 * locale changes; `actions.test.ts` additionally pins the literal value,
 * because the name is a wire format a live browser already holds.
 */
export const LOCALE_COOKIE_NAME = 'locale';

/**
 * A year, in seconds. A cookie with neither `maxAge` nor `expires` is a
 * session cookie -- the browser drops it on close. There is no user-profile
 * field behind this preference, so this lifetime *is* how long the app
 * remembers a person's language, and leaving it unset reads to them as the
 * switch not working at all.
 */
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;
