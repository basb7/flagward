import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.35],
  ['month', 12],
  ['year', Number.POSITIVE_INFINITY],
];

/** "3 minutes ago" style label for an ISO timestamp. */
export function formatRelativeTime(isoTimestamp: string) {
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  let value = (Date.parse(isoTimestamp) - Date.now()) / 1000;

  for (const [unit, step] of RELATIVE_UNITS) {
    if (Math.abs(value) < step) {
      return formatter.format(Math.round(value), unit);
    }
    value /= step;
  }

  return formatter.format(Math.round(value), 'year');
}

/** Absolute timestamp for tooltips and dense log tables. */
export function formatTimestamp(isoTimestamp: string) {
  return new Date(isoTimestamp).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * Validates a `?next=` redirect target carried through login/register, so an
 * invitation link (or any other URL a person didn't type themselves) can
 * never turn this into an open redirect. Only a same-origin, path-rooted
 * destination is honoured; everything else falls back to `fallback`.
 *
 * Rejected on purpose:
 * - A value with a scheme (`https://evil.com`, `javascript:...`) -- it
 *   doesn't start with `/`, since a bare path never contains a colon before
 *   its first slash.
 * - A protocol-relative value (`//evil.com`) -- browsers resolve this as
 *   "same scheme, different host", which is an open redirect off this origin.
 * - A backslash-led value (`/\evil.com`, `\\evil.com`) -- some browsers
 *   normalize a leading backslash into a protocol-relative `//` before
 *   navigating, so it gets the same rejection as one.
 */
export function safeNextPath(
  next: string | null | undefined,
  fallback = '/dashboard',
) {
  if (!next) return fallback;
  if (
    !next.startsWith('/') ||
    next.startsWith('//') ||
    next.startsWith('/\\')
  ) {
    return fallback;
  }
  // Resolve before judging, and return what was judged.
  //
  // Checking the raw string and then handing the raw string onward leaves a
  // gap: `/..//evil.com` keeps the dummy origin, so an origin-only check
  // passes it, but it *resolves* to the pathname `//evil.com`. Whatever
  // normalises the path before navigating then produces a protocol-relative
  // URL, and the browser reads that as another host -- the exact off-site
  // redirect this function exists to prevent.
  //
  // So: resolve first, reject a resolved path that is protocol-relative, and
  // return the normalised path rather than the input, so the value that
  // travels onward is the one that was actually checked.
  try {
    const resolved = new URL(next, 'http://invalid.invalid');
    if (resolved.origin !== 'http://invalid.invalid') return fallback;
    if (resolved.pathname.startsWith('//')) return fallback;
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return fallback;
  }
}
