import { afterEach, describe, expect, it, vi } from 'vitest';
import { formatRelativeTime, formatTimestamp, safeNextPath } from './utils.ts';

describe('safeNextPath', () => {
  // A fixed, unrelated origin to resolve candidate results against. If a
  // result ever resolves to a different origin, it is an open redirect.
  const SITE_ORIGIN = 'http://flagward.invalid';

  /**
   * The property under test: whatever safeNextPath returns must be a path
   * rooted at this app's own origin. Resolving it can never change the
   * origin, and it can never be protocol-relative ("//host/..."), which
   * browsers read as "same scheme, different host".
   *
   * This is deliberately NOT "result === fallback": a same-origin path that
   * differs from the fallback (e.g. a percent-encoded path segment that
   * still lives on this origin) is a correct answer, not a bypass.
   */
  function assertStaysOnOrigin(
    input: string | null | undefined,
    result: string,
  ) {
    expect(
      result.startsWith('/'),
      `safeNextPath(${JSON.stringify(input)}) => ${JSON.stringify(result)} is not path-rooted`,
    ).toBe(true);
    expect(
      result.startsWith('//'),
      `safeNextPath(${JSON.stringify(input)}) => ${JSON.stringify(result)} is protocol-relative`,
    ).toBe(false);
    const resolved = new URL(result, SITE_ORIGIN);
    expect(
      resolved.origin,
      `safeNextPath(${JSON.stringify(input)}) => ${JSON.stringify(result)} resolves off-origin (${resolved.origin})`,
    ).toBe(SITE_ORIGIN);
  }

  // Every one of these has been used, somewhere, to smuggle a foreign host
  // through a "same-origin path" check. None of them may ever navigate
  // off-site, regardless of what string safeNextPath actually returns.
  const maliciousInputs = [
    '//evil.com',
    '///evil.com',
    '/\\evil.com',
    '/\\\\evil.com',
    'https://evil.com',
    'http://evil.com',
    'javascript:alert(1)',
    '//evil.com/path',
    '/..//evil.com',
    '/./../..//evil.com',
    '/\r\n//evil.com',
    ' //evil.com',
    'evil.com',
    '\\\\evil.com',
    '/%09/evil.com',
    '/%2F%2Fevil.com',
    '/\tevil.com',
    // Extra cases beyond the required list.
    '/\x00//evil.com', // NUL byte before the protocol-relative prefix
    '//\\evil.com', // protocol-relative, backslash host separator
    '/\\/evil.com', // backslash then slash
    '\r\n//evil.com', // no leading "/" at all once you look past the CRLF
    '/\v//evil.com', // vertical tab
    '/／／evil.com', // fullwidth solidus lookalike for "//"
    '   ', // whitespace only, no leading "/"
  ];

  it('never resolves any malicious input off-site', () => {
    for (const input of maliciousInputs) {
      const result = safeNextPath(input);
      assertStaysOnOrigin(input, result);
    }
  });

  it('never resolves a malicious input off-site, even with a custom fallback', () => {
    for (const input of maliciousInputs) {
      const result = safeNextPath(input, '/login');
      assertStaysOnOrigin(input, result);
    }
  });

  it('falls back for every input with no leading "/" or an unparseable scheme', () => {
    // These have no legitimate same-origin reading at all, so (unlike the
    // property test above) asserting the exact fallback is appropriate here.
    const alwaysFallback = [
      '//evil.com',
      '///evil.com',
      'https://evil.com',
      'http://evil.com',
      'javascript:alert(1)',
      '//evil.com/path',
      ' //evil.com',
      'evil.com',
      '\\\\evil.com',
      '\r\n//evil.com',
      '   ',
    ];
    for (const input of alwaysFallback) {
      expect(safeNextPath(input)).toBe('/dashboard');
    }
  });

  it('rejects the resolved-path bypass: "/..//evil.com" no longer reaches "//evil.com"', () => {
    // This is the exact bypass this function was fixed for: an origin-only
    // check on the raw string sees a same-origin path, but the resolved
    // pathname is protocol-relative. Pin both cases down explicitly.
    expect(safeNextPath('/..//evil.com')).toBe('/dashboard');
    expect(safeNextPath('/./../..//evil.com')).toBe('/dashboard');
  });

  it('keeps a same-origin path whose escaped/control bytes merely look suspicious', () => {
    // These stay on this origin once resolved -- they are safe, even though
    // they are not equal to the fallback. Pinning the exact values guards
    // against a future change accidentally over- or under-blocking them.
    expect(safeNextPath('/%09/evil.com')).toBe('/%09/evil.com');
    expect(safeNextPath('/%2F%2Fevil.com')).toBe('/%2F%2Fevil.com');
    // A literal (unescaped) tab is stripped by URL parsing, collapsing the
    // path to "/evil.com" -- still a same-origin path, not a host.
    expect(safeNextPath('/\tevil.com')).toBe('/evil.com');
  });

  it('passes legitimate same-origin paths through unchanged, including query and hash', () => {
    const legitimate = [
      '/dashboard',
      '/invite/abc123',
      '/dashboard/members?tab=x',
      '/dashboard#top',
    ];
    for (const path of legitimate) {
      expect(safeNextPath(path)).toBe(path);
    }
  });

  it('falls back to "/dashboard" by default for null, undefined, and empty input', () => {
    expect(safeNextPath(null)).toBe('/dashboard');
    expect(safeNextPath(undefined)).toBe('/dashboard');
    expect(safeNextPath('')).toBe('/dashboard');
  });

  it('honours a custom fallback', () => {
    expect(safeNextPath(null, '/login')).toBe('/login');
    expect(safeNextPath('https://evil.com', '/login')).toBe('/login');
  });

  it('passes a bare "/" through unchanged', () => {
    expect(safeNextPath('/')).toBe('/');
  });
});

describe('formatRelativeTime', () => {
  const FIXED_NOW = Date.UTC(2026, 0, 1, 12, 0, 0);

  function at(deltaMs: number): string {
    return new Date(FIXED_NOW + deltaMs).toISOString();
  }

  /**
   * Only `Date` is faked, exactly as `node:test`'s
   * `t.mock.timers.enable({ apis: ['Date'] })` did. Faking the timer APIs too
   * would stall anything in the runtime that waits on one.
   *
   * `node:test` restored its clock when the test ended; Vitest's does not, so
   * the `afterEach` below is what replaces that.
   */
  function freezeClock() {
    vi.useFakeTimers({ toFake: ['Date'], now: FIXED_NOW });
  }

  afterEach(() => {
    vi.useRealTimers();
  });

  it('reports "now" at exactly zero difference', () => {
    freezeClock();
    expect(formatRelativeTime(at(0))).toBe('now');
  });

  it('stays in seconds just under the one-minute boundary', () => {
    freezeClock();
    expect(formatRelativeTime(at(-59_000))).toBe('59 seconds ago');
  });

  it('rolls over to "1 minute ago" exactly at the one-minute boundary', () => {
    // RELATIVE_UNITS compares with a strict "<", so a difference exactly
    // equal to a step size belongs to the *next* unit up, not the last one.
    freezeClock();
    expect(formatRelativeTime(at(-60_000))).toBe('1 minute ago');
  });

  it('reports future timestamps as "in X", not "ago"', () => {
    freezeClock();
    expect(formatRelativeTime(at(30_000))).toBe('in 30 seconds');
    expect(formatRelativeTime(at(60_000))).toBe('in 1 minute');
  });

  it('does not throw on a malformed timestamp', () => {
    freezeClock();
    // Date.parse('not-a-date') is NaN, so the elapsed-seconds value is NaN.
    // Intl.RelativeTimeFormat#format throws a RangeError on a non-finite
    // value, so this must be guarded explicitly rather than left to throw.
    expect(formatRelativeTime('not-a-date')).toBe('Invalid Date');
    expect(formatRelativeTime('')).toBe('Invalid Date');
  });
});

describe('formatTimestamp', () => {
  it('formats a valid ISO timestamp', () => {
    const formatted = formatTimestamp('2026-01-01T12:00:00.000Z');
    // Locale-dependent, but must at least mention the day and year context
    // a person would need to disambiguate it from "today".
    expect(formatted).toMatch(/Jan/);
    expect(formatted).toMatch(/1/);
  });

  it('reports "Invalid Date" for a malformed timestamp, without throwing', () => {
    expect(formatTimestamp('not-a-date')).toBe('Invalid Date');
    expect(formatTimestamp('')).toBe('Invalid Date');
  });
});
