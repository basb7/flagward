import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { ERROR_COPY, errorCopy } from './error-copy';

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

describe('the error copy table', () => {
  /**
   * The reason this file exists. An unmapped code still reaches the user --
   * as itself -- so nothing looks broken when copy is missing, and without
   * this test a new code ships unwritten and nobody notices until somebody
   * reads `project_limit_reached` in a dialog.
   */
  it('covers every error code the backend can answer with', () => {
    const codes = backendErrorCodes();

    expect(codes.size).toBeGreaterThan(0); // the walk found the backend at all

    const missing = [...codes].filter((code) => !(code in ERROR_COPY)).sort();
    expect(missing).toEqual([]);
  });

  it('has no copy for codes the backend cannot send', () => {
    const codes = backendErrorCodes();

    const stale = Object.keys(ERROR_COPY)
      .filter((code) => !codes.has(code))
      .sort();
    expect(stale).toEqual([]);
  });
});

describe('errorCopy', () => {
  it('translates a code it knows', () => {
    expect(errorCopy('invitation_expired')).toBe(
      'This invitation has expired.',
    );
  });

  it('returns an unknown code as itself, so it stays traceable', () => {
    expect(errorCopy('something_new')).toBe('something_new');
  });

  it('prefers a caller fallback for an unknown code', () => {
    expect(errorCopy('something_new', 'This link is not valid.')).toBe(
      'This link is not valid.',
    );
  });

  it('ignores the fallback when it knows the code', () => {
    expect(errorCopy('invitation_expired', 'This link is not valid.')).toBe(
      'This invitation has expired.',
    );
  });
});
