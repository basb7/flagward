import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CreateEnvironmentDialog } from '@/components/dashboard/create-environment-dialog';
import { CreateOrganizationDialog } from '@/components/dashboard/create-organization-dialog';
import { CreateProjectDialog } from '@/components/dashboard/create-project-dialog';
import { Button } from '@/components/ui/button';

const success = vi.fn();
const showError = vi.fn();

vi.mock('@/lib/toast-context', () => ({
  useToast: () => ({ success, error: showError, info: vi.fn() }),
}));

vi.mock('@/lib/api', () => ({
  tenancyApi: {
    createOrganization: vi.fn(),
    createProject: vi.fn(),
  },
  environmentsApi: {
    create: vi.fn(),
  },
}));

import type { Environment, Organization, Project } from '@/lib/api';
import { environmentsApi, tenancyApi } from '@/lib/api';

/**
 * The union of what the three dialogs hand back. Typing the shared `onCreated`
 * this way lets one table drive all three: a handler taking the union is
 * accepted wherever a handler taking one member is expected.
 */
type CreatedResource = Organization | Project | Environment;

const createOrganization = vi.mocked(tenancyApi.createOrganization);
const createProject = vi.mocked(tenancyApi.createProject);
const createEnvironment = vi.mocked(environmentsApi.create);

/**
 * The three create dialogs are the same form three times over -- one required
 * name, a Create button gated on it -- so they are covered as one table
 * rather than as three near-identical files. Anything genuinely specific to
 * one of them (the payload it POSTs, the fields it does *not* ask for) is
 * asserted per case below.
 */
const CASES = [
  {
    label: 'CreateOrganizationDialog',
    fieldLabel: 'Name',
    toast: 'Organization created successfully',
    api: createOrganization,
    expectedPayload: { name: 'Acme Inc' },
    typed: 'Acme Inc',
    created: { id: 'org-1', name: 'Acme Inc' },
    render: (onCreated: (value: CreatedResource) => void) => (
      <CreateOrganizationDialog
        triggerButton={<Button />}
        triggerContent="New organization"
        onCreated={onCreated}
      />
    ),
  },
  {
    label: 'CreateProjectDialog',
    fieldLabel: 'Name',
    toast: 'Project created successfully',
    api: createProject,
    expectedPayload: { organization: 'org-1', name: 'Mobile App' },
    typed: 'Mobile App',
    created: { id: 'proj-1', name: 'Mobile App' },
    render: (onCreated: (value: CreatedResource) => void) => (
      <CreateProjectDialog
        organizationId="org-1"
        triggerButton={<Button />}
        triggerContent="New project"
        onCreated={onCreated}
      />
    ),
  },
  {
    label: 'CreateEnvironmentDialog',
    fieldLabel: 'Name',
    toast: 'Environment created successfully',
    api: createEnvironment,
    expectedPayload: { project: 'proj-1', name: 'Production' },
    typed: 'Production',
    created: { id: 'env-1', name: 'Production' },
    render: (onCreated: (value: CreatedResource) => void) => (
      <CreateEnvironmentDialog
        projectId="proj-1"
        triggerButton={<Button />}
        triggerContent="New environment"
        onCreated={onCreated}
      />
    ),
  },
] as const;

beforeEach(() => {
  success.mockReset();
  showError.mockReset();
  createOrganization.mockReset();
  createProject.mockReset();
  createEnvironment.mockReset();
});

const createButton = () => screen.getByRole('button', { name: 'Create' });

for (const testCase of CASES) {
  describe(testCase.label, () => {
    async function open(onCreated = vi.fn()) {
      render(testCase.render(onCreated));
      fireEvent.click(screen.getByRole('button', { name: /^New / }));
      await waitFor(() =>
        expect(screen.getByLabelText(testCase.fieldLabel)).toBeInTheDocument(),
      );
      return onCreated;
    }

    it('opens with an empty name and Create disabled', async () => {
      await open();

      expect(screen.getByLabelText(testCase.fieldLabel)).toHaveValue('');
      expect(createButton()).toBeDisabled();
    });

    it('enables Create once the name is filled', async () => {
      await open();

      fireEvent.change(screen.getByLabelText(testCase.fieldLabel), {
        target: { value: testCase.typed },
      });

      expect(createButton()).toBeEnabled();
    });

    it('disables Create again when the name is cleared', async () => {
      await open();

      fireEvent.change(screen.getByLabelText(testCase.fieldLabel), {
        target: { value: testCase.typed },
      });
      fireEvent.change(screen.getByLabelText(testCase.fieldLabel), {
        target: { value: '' },
      });

      expect(createButton()).toBeDisabled();
    });

    it('POSTs the name and hands the created resource back', async () => {
      // biome-ignore lint/suspicious/noExplicitAny: one table drives three differently-typed APIs
      (testCase.api as any).mockResolvedValue(testCase.created);
      const onCreated = await open();

      fireEvent.change(screen.getByLabelText(testCase.fieldLabel), {
        target: { value: testCase.typed },
      });
      fireEvent.click(createButton());

      await waitFor(() =>
        expect(testCase.api).toHaveBeenCalledWith(testCase.expectedPayload),
      );
      await waitFor(() =>
        expect(onCreated).toHaveBeenCalledWith(testCase.created),
      );
      expect(success).toHaveBeenCalledWith(testCase.toast);
    });

    it('reports the backend message and creates nothing when the POST fails', async () => {
      // biome-ignore lint/suspicious/noExplicitAny: one table drives three differently-typed APIs
      (testCase.api as any).mockRejectedValue(
        new Error('That name is already taken'),
      );
      const onCreated = await open();

      fireEvent.change(screen.getByLabelText(testCase.fieldLabel), {
        target: { value: testCase.typed },
      });
      fireEvent.click(createButton());

      await waitFor(() =>
        expect(showError).toHaveBeenCalledWith('That name is already taken'),
      );
      expect(onCreated).not.toHaveBeenCalled();
      expect(success).not.toHaveBeenCalled();
    });
  });
}

describe('the create dialogs as a group', () => {
  it('never asks for a key: the server derives it from the name', async () => {
    // Projects and environments used to make the person invent a key. They
    // no longer do, and re-adding that field is the regression this catches.
    for (const testCase of CASES) {
      const { unmount } = render(testCase.render(vi.fn()));
      fireEvent.click(screen.getByRole('button', { name: /^New / }));
      await waitFor(() =>
        expect(screen.getByLabelText('Name')).toBeInTheDocument(),
      );

      expect(screen.queryByLabelText(/key/i)).not.toBeInTheDocument();
      expect(screen.getAllByRole('textbox', { hidden: false })).toHaveLength(1);

      unmount();
    }
  });
});
