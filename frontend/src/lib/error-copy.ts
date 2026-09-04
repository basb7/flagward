/**
 * The backend's error codes, and what a person should read instead.
 *
 * Endpoints that distinguish their failures answer with a machine code --
 * `{"error": "seat_limit_reached"}` -- rather than a sentence, and `api.ts`
 * surfaces that code as the `ApiError`'s message. Copy belongs here and not
 * there: changing what somebody reads should not be a backend deploy, and the
 * same failure reaches more than one screen.
 *
 * A code with no entry falls through as itself. That is deliberate. A generic
 * "something went wrong" throws away the one piece of information anybody had,
 * and the person most likely to see an unmapped code is whoever just added it.
 *
 * `errorCopyCoverage.test.ts` reads the codes out of the backend and fails if
 * one is missing from this table, so an addition cannot ship unwritten.
 */
export const ERROR_COPY: Record<string, string> = {
  // Invitations
  already_a_member: 'You are already a member of this organization.',
  invitation_already_used: 'This invitation has already been used.',
  invitation_expired: 'This invitation has expired.',
  invitation_not_found: 'This invitation no longer exists.',
  invitation_revoked: 'This invitation has been revoked.',
  seat_limit_reached:
    'This organization has no seats left. Ask an admin to free one up or upgrade the plan, then try again.',

  // Membership
  last_admin_cannot_be_demoted:
    'An organization must keep at least one admin. Promote somebody else first.',
  last_admin_cannot_be_removed:
    'An organization must keep at least one admin. Promote somebody else first.',

  // Deletion
  organization_has_other_members:
    'Remove everybody else from this organization before deleting it.',

  // Plan ceilings
  project_limit_reached:
    'This organization has reached the number of projects its plan allows.',

  // Password reset
  token_already_used: 'This password reset link has already been used.',
  token_expired: 'This password reset link has expired. Ask for a new one.',
  token_not_found: 'This password reset link is not valid.',
};

/**
 * Copy for a backend error code.
 *
 * Unmapped codes are returned as they arrived, so a failure nobody wrote copy
 * for is still traceable to the endpoint that produced it. A screen where an
 * unrecognised failure has a better meaning of its own -- an invitation page,
 * where anything unexpected means the link is dead -- passes that as
 * `fallback`.
 */
export function errorCopy(code: string, fallback?: string): string {
  return ERROR_COPY[code] ?? fallback ?? code;
}
