import { cookies } from 'next/headers';
import { getRequestConfig } from 'next-intl/server';
import { DEFAULT_LOCALE, isLocale, LOCALE_COOKIE_NAME } from '@/i18n/locales';

export default getRequestConfig(async () => {
  const store = await cookies();
  const cookieValue = store.get(LOCALE_COOKIE_NAME)?.value;

  // A cookie is user-controlled input, and the value below feeds a dynamic
  // `import()`. Without this guard, a crafted `locale` cookie becomes a
  // dynamic import of an arbitrary path rather than a language choice.
  const locale =
    cookieValue && isLocale(cookieValue) ? cookieValue : DEFAULT_LOCALE;

  const messages = (await import(`../../messages/${locale}.json`)).default;

  return { locale, messages };
});
