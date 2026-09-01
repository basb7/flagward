import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end configuration.
 *
 * These tests drive the *whole* product in a real browser: Postgres, Django
 * and Next.js. There is deliberately no `webServer` block here. Starting only
 * `next dev` would give a dashboard whose every request 500s, and the failure
 * would surface as a timed-out selector three steps into the chain rather than
 * as "the API is not running". `e2e/global-setup.ts` checks both halves of the
 * stack up front and says exactly which one is missing.
 *
 * Prerequisite, from the repository root:
 *
 *     docker compose -f compose.dev.yml up -d
 */

/** Where the dashboard is served. */
export const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';

/**
 * Where the API is served. The browser bundle talks to whatever
 * `NEXT_PUBLIC_API_URL` was baked in at build time (compose.dev.yml sets
 * `http://localhost:8000`), so the readiness probe checks the same origin.
 */
export const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',

  // The onboarding chain is one ordered story against one shared stack.
  // Running it alone keeps failures readable and avoids two runs racing for
  // the same dev database.
  fullyParallel: false,
  workers: 1,

  forbidOnly: !!process.env.CI,
  // A run that dies on a flaky network hop is not a product failure, but a
  // second local run should not quietly paper over a real one.
  retries: process.env.CI ? 1 : 0,

  reporter: process.env.CI
    ? [['github'], ['html', { open: 'never' }]]
    : [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },

  // Chromium only: a second engine costs another browser download and another
  // few minutes of CI for insight this suite is not yet deep enough to give.
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
