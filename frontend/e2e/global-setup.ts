import { API_URL, BASE_URL } from '../playwright.config';

/**
 * Refuse to start until the real stack answers.
 *
 * Without this, a missing API produces the worst possible failure: the browser
 * loads the dashboard fine, every fetch fails silently, and Playwright reports
 * a 30-second timeout waiting for an empty state that was never going to
 * render. The message below names the one command that fixes it instead.
 */

const READY_TIMEOUT_MS = Number(process.env.E2E_READY_TIMEOUT_MS ?? 60_000);
const POLL_INTERVAL_MS = 1_000;

const COMPOSE_HINT = `The end-to-end suite drives the real stack -- Postgres, Django and Next.js.
Start it from the repository root and try again:

    docker compose -f compose.dev.yml up -d`;

const sleep = (ms: number) =>
  new Promise((resolve) => setTimeout(resolve, ms));

async function probe(url: string): Promise<string | null> {
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(5_000),
    });
    return response.ok ? null : `HTTP ${response.status}`;
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
}

async function waitFor(label: string, url: string) {
  const deadline = Date.now() + READY_TIMEOUT_MS;
  let lastFailure = 'not attempted';

  while (Date.now() < deadline) {
    const failure = await probe(url);
    if (failure === null) return;
    lastFailure = failure;
    await sleep(POLL_INTERVAL_MS);
  }

  throw new Error(
    `Flagward's ${label} is not reachable at ${url}.\n\n` +
      `${COMPOSE_HINT}\n\n` +
      `Gave up after ${Math.round(READY_TIMEOUT_MS / 1000)}s. ` +
      `Last attempt: ${lastFailure}.`,
  );
}

export default async function globalSetup() {
  // The API first: it is the half that is actually missing when someone runs
  // `npm run dev` and then reaches for `test:e2e`.
  await waitFor('API', `${API_URL}/api/v1/health/`);
  await waitFor('dashboard', `${BASE_URL}/login`);
}
