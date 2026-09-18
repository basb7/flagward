import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom has no PointerEvent constructor. Base UI's interactive primitives
// (e.g. Switch) dispatch one internally on click, so without this polyfill
// every test that clicks them throws instead of toggling state.
if (typeof window.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
    }
  }
  // @ts-expect-error -- partial polyfill, only what Base UI dispatches.
  window.PointerEvent = PointerEventPolyfill;
}

// Every test renders into the same jsdom document. Without this, a component
// left mounted by one test is still found by the next one's queries, and a
// suite that passes in order fails when a single test is run alone.
afterEach(() => {
  cleanup();
});
