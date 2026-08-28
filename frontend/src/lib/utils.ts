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
