'use server';

import { cookies } from 'next/headers';
import {
  isLocale,
  LOCALE_COOKIE_MAX_AGE,
  LOCALE_COOKIE_NAME,
  type Locale,
} from '@/i18n/locales';

/**
 * The only way this app changes locale -- there is no `middleware.ts` and no
 * locale segment in the URL, so a cookie set here is what `request.ts` reads
 * on the next request. `isLocale` guards the boundary anyway: a server
 * action is still a network-reachable entry point, and its argument is only
 * as trustworthy as whatever called it.
 *
 * Lives in its own file rather than inlined in `layout.tsx`: Next bundles an
 * inlined action's *whole containing module* into the client the moment a
 * Client Component imports it, and `DashboardNav` -- which mounts the
 * language switcher -- sits behind `dashboard/layout.tsx`, a nested route
 * layout that only ever receives `children` from the root layout, not a
 * prop. Importing `changeLocaleAction` straight out of `app/layout.tsx`
 * turned that whole Server Component (next/font, `cookies()`,
 * `generateMetadata`) into a Client Component and broke the build; a file
 * whose only export is a `"use server"` function has nothing else to drag
 * along.
 */
export async function changeLocaleAction(locale: Locale) {
  if (!isLocale(locale)) return;
  const store = await cookies();
  store.set(LOCALE_COOKIE_NAME, locale, {
    maxAge: LOCALE_COOKIE_MAX_AGE,
    path: '/',
    // Nothing client-side reads this -- `useLocale()` takes the locale from
    // the server-rendered intl provider -- so denying page scripts access
    // costs nothing.
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
  });
}
