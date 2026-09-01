import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

/**
 * Unit and component tests.
 *
 * This is the *only* test runner for `src/**`: `npm test` runs it, and CI's
 * "Frontend (lint + build)" job runs `npm test`. A second runner alongside it
 * would mean a test could be written in the one CI does not execute.
 *
 * `e2e/` is deliberately excluded -- those specs are Playwright's and import
 * `@playwright/test`, which would fail under Vitest. They run in their own CI
 * job via `npm run test:e2e`.
 */
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**', '.next/**'],
    restoreMocks: true,
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  esbuild: {
    jsx: 'automatic',
  },
});
