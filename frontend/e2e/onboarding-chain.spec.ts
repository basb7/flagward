import { expect, type Locator, type Page, test } from '@playwright/test';

/**
 * The onboarding chain: register -> organization -> project -> environment.
 *
 * This is deliberately ONE test rather than four. Each link only exists
 * because the previous one completed, and every integration bug this suite was
 * written for lived in a *seam*: capabilities cached at mount going stale the
 * moment an organization was created, a page that told you to create a project
 * and offered no button to do it, a chain whose last link had no action.
 * Four independent tests that each seed their own state would have passed
 * through all three.
 */

/**
 * Registration needs a username and email nobody has used, and the dev
 * database is not reset between runs. One stamp, reused across all four names,
 * keeps a run's leftovers recognisable as belonging together.
 *
 * Generated inside the test body rather than at module scope, so a retry gets
 * its own identity instead of colliding with the attempt that just failed.
 */
function newRunFixture() {
  const id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  return {
    username: `e2e-${id}`,
    email: `e2e-${id}@flagward.test`,
    // Must clear Django's AUTH_PASSWORD_VALIDATORS: long enough, not numeric,
    // not a common password, and not similar to the username or email above --
    // which is why the run id is deliberately absent from it.
    password: 'Fl4gward-onboarding-e2e',
    organizationName: `E2E Org ${id}`,
    projectName: `E2E Project ${id}`,
    environmentName: `E2E Env ${id}`,
  };
}

/** The dashboard truncates an API key to its first 16 characters. */
const TRUNCATED_API_KEY = /\S{16}\.\.\./;

/**
 * Opens one of the three create dialogs, fills its only field and submits.
 *
 * All three share the same shape -- a trigger button, a titled dialog, a
 * "Name" field and a "Create" button -- so asserting the title is what keeps
 * this helper honest about which dialog it actually opened.
 */
async function createNamedResource(
  page: Page,
  { trigger, dialogTitle, name }: {
    trigger: string;
    dialogTitle: string;
    name: string;
  },
) {
  await page.getByRole('button', { name: trigger, exact: true }).click();

  const dialog: Locator = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: dialogTitle })).toBeVisible();

  await dialog.getByLabel('Name').fill(name);
  await dialog.getByRole('button', { name: 'Create', exact: true }).click();

  // The dialog closes only once the POST resolved, so this is also the wait
  // for the resource to exist.
  await expect(dialog).toBeHidden();
}

test('a new account can register and walk the whole chain to a working environment', async ({
  page,
}) => {
  const run = newRunFixture();

  await test.step('register a new account', async () => {
    await page.goto('/register');

    await page.getByLabel('Username').fill(run.username);
    await page.getByLabel('Email').fill(run.email);
    await page.getByLabel('Password').fill(run.password);
    await page.getByRole('button', { name: 'Create account' }).click();

    // Still on /register means the API rejected the registration; the failure
    // screenshot carries the banner explaining why.
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  await test.step('an account with no organization is asked to create one', async () => {
    await expect(
      page.getByText('Create your organization', { exact: true }),
    ).toBeVisible();
  });

  await test.step('create the organization', async () => {
    await createNamedResource(page, {
      trigger: 'Create organization',
      dialogTitle: 'Create organization',
      name: run.organizationName,
    });

    await expect(page.getByLabel('Organization')).toHaveText(
      run.organizationName,
    );
  });

  await test.step('the new organization offers creating a project, not a locked-out message', async () => {
    // The regression this test exists for. `/auth/me/` answers the caller's
    // capabilities, the dashboard reads them from state captured at mount, and
    // creating an organization changes them. When the refresh was missing, the
    // brand-new admin of a brand-new organization was told they had no access
    // to any project in it and given nothing to click.
    await expect(
      page.getByText('Create your first project', { exact: true }),
    ).toBeVisible();
    await expect(page.getByText('No project access yet')).toHaveCount(0);
  });

  await test.step('create the project', async () => {
    await createNamedResource(page, {
      trigger: 'Create project',
      dialogTitle: 'Create project',
      name: run.projectName,
    });

    await expect(page.getByLabel('Project')).toHaveValue(/.+/);
  });

  await test.step('the project offers creating an environment', async () => {
    // The other dead end: the Environments card said "No environments yet" and
    // stopped there, because its action was only rendered when a project was
    // already selected.
    await expect(page.getByText('No environments yet')).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Create environment', exact: true }),
    ).toBeVisible();
  });

  await test.step('create the environment', async () => {
    await createNamedResource(page, {
      trigger: 'Create environment',
      dialogTitle: 'Create environment',
      name: run.environmentName,
    });

    // The Environments card lists it as a link through to the environments
    // page. (The name also lands in the dashboard's environment filter, so
    // matching on bare text here would be ambiguous.)
    await expect(
      page.getByRole('link', { name: run.environmentName }),
    ).toBeVisible();
  });

  await test.step('a direct visit to /dashboard/environments lists it with its API key', async () => {
    // A full page load, not a client-side link: this is the URL someone
    // bookmarks, and it has to restore the selected project from scratch
    // rather than land on a spinner or an empty-state dead end.
    await page.goto('/dashboard/environments');

    await expect(
      page.getByRole('heading', { name: 'Environments', level: 1 }),
    ).toBeVisible();

    const row = page.getByRole('row').filter({ hasText: run.environmentName });
    await expect(row).toHaveCount(1);

    // An environment is only usable once it has an API key an SDK can send.
    await expect(
      row.getByRole('cell').filter({ hasText: TRUNCATED_API_KEY }),
    ).toHaveCount(1);
  });
});
