'use client';

import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Spinner } from '@/components/ui/spinner';
import { ApiError, invitationsApi } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { errorCopy } from '@/lib/error-copy';
import { useToast } from '@/lib/toast-context';

/**
 * The backend answers every invalid preview state -- unknown, expired,
 * revoked, already used -- with the identical generic 404, deliberately, so
 * this screen can never become a way to probe a token. Whatever the reason,
 * there is exactly one honest message for it.
 */
const INVALID_LINK_MESSAGE = 'This invitation link is not valid any more.';

type PreviewState =
  | { status: 'loading' }
  | { status: 'invalid' }
  | { status: 'ready'; organizationName: string; role: string };

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { success, error: showError, info } = useToast();
  const { user, isLoading: isAuthLoading, logout } = useAuth();

  const [preview, setPreview] = useState<PreviewState>({ status: 'loading' });
  const [isAccepting, setIsAccepting] = useState(false);

  const loadPreview = useCallback(async () => {
    setPreview({ status: 'loading' });
    try {
      const response = await invitationsApi.preview(token);
      setPreview({
        status: 'ready',
        organizationName: response.organization_name,
        role: response.role,
      });
    } catch {
      // Every failure reason collapses to the same message -- see
      // INVALID_LINK_MESSAGE above.
      setPreview({ status: 'invalid' });
    }
  }, [token]);

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  const returnHere = `/invite/${token}`;

  const handleAccept = async () => {
    setIsAccepting(true);
    try {
      await invitationsApi.accept(token);
      success('Invitation accepted -- welcome aboard.');
      router.push('/dashboard');
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.message === 'already_a_member') {
          info(errorCopy('already_a_member'));
          router.push('/dashboard');
          return;
        }
        // Anything with no copy means the token itself is dead, which is
        // more useful on this page than the code would be.
        showError(errorCopy(err.message, INVALID_LINK_MESSAGE));
        // Every other code means the token itself is now dead, except a
        // seat-limit failure -- that one can resolve once an admin frees a
        // seat or upgrades the plan, so the confirm action stays available.
        if (err.message !== 'seat_limit_reached') {
          setPreview({ status: 'invalid' });
        }
      } else {
        showError('Failed to accept the invitation.');
      }
    } finally {
      setIsAccepting(false);
    }
  };

  const handleSignOutAndSwitch = async () => {
    await logout();
    router.push(`/login?next=${encodeURIComponent(returnHere)}`);
  };

  if (preview.status === 'loading' || isAuthLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Spinner size="lg" />
      </div>
    );
  }

  if (preview.status === 'invalid') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Invitation not valid</CardTitle>
            <CardDescription>{INVALID_LINK_MESSAGE}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-bold text-foreground">
            You&apos;re invited
          </CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-1.5">
            Join{' '}
            <strong className="text-foreground">
              {preview.organizationName}
            </strong>{' '}
            as
            <Badge variant={preview.role === 'ADMIN' ? 'warning' : 'muted'}>
              {preview.role}
            </Badge>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {user ? (
            <div className="space-y-2 rounded-md border border-border bg-muted p-3 text-sm">
              <p className="text-muted-foreground">
                Signed in as{' '}
                <strong className="text-foreground">{user.username}</strong>
                {user.email ? ` (${user.email})` : ''}. Confirming joins{' '}
                <strong className="text-foreground">this account</strong> to{' '}
                {preview.organizationName}.
              </p>
              <button
                type="button"
                onClick={handleSignOutAndSwitch}
                className="text-xs text-muted-foreground underline-offset-4 hover:underline"
              >
                Not you? Sign out and sign in as someone else
              </button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Sign in or create an account to accept. You&apos;ll be brought
              right back here.
            </p>
          )}
        </CardContent>
        <CardFooter className="flex flex-col gap-3">
          {user ? (
            <Button
              className="w-full"
              onClick={handleAccept}
              disabled={isAccepting}
            >
              {isAccepting ? <Spinner size="sm" className="mr-2" /> : null}
              Accept invitation
            </Button>
          ) : (
            <>
              <Button
                className="w-full"
                onClick={() =>
                  router.push(`/login?next=${encodeURIComponent(returnHere)}`)
                }
              >
                Sign in
              </Button>
              <Button
                variant="outline"
                className="w-full"
                onClick={() =>
                  router.push(
                    `/register?next=${encodeURIComponent(returnHere)}`,
                  )
                }
              >
                Create an account
              </Button>
            </>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}
