import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Every test renders into the same jsdom document. Without this, a component
// left mounted by one test is still found by the next one's queries, and a
// suite that passes in order fails when a single test is run alone.
afterEach(() => {
  cleanup();
});
