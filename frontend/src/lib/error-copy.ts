import { useTranslations } from 'next-intl';
import { useCallback } from 'react';

/**
 * The backend's error codes, and what a person should read instead.
 *
 * Endpoints that distinguish their failures answer with a machine code --
 * `{"error": "seat_limit_reached"}` -- rather than a sentence, and `api.ts`
 * surfaces that code as the `ApiError`'s message. Copy lives in the `errors`
 * namespace of `messages/*.json` and not in the backend: changing what
 * somebody reads should not be a backend deploy, the same failure reaches
 * more than one screen, and it now needs a translation rather than one
 * English sentence.
 *
 * A code with no entry falls through as itself. That is deliberate. A generic
 * "something went wrong" throws away the one piece of information anybody had,
 * and the person most likely to see an unmapped code is whoever just added it.
 *
 * `error-copy.test.ts` reads the codes out of the backend and fails if one is
 * missing from either locale's `errors` namespace, so an addition cannot ship
 * unwritten or half-translated.
 */
export function useErrorCopy() {
  const t = useTranslations('errors');

  /**
   * Copy for a backend error code.
   *
   * Unmapped codes are returned as they arrived, so a failure nobody wrote
   * copy for is still traceable to the endpoint that produced it. A screen
   * where an unrecognised failure has a better meaning of its own -- an
   * invitation page, where anything unexpected means the link is dead --
   * passes that as `fallback`.
   */
  return useCallback(
    (code: string, fallback?: string): string =>
      t.has(code) ? t(code) : (fallback ?? code),
    [t],
  );
}
