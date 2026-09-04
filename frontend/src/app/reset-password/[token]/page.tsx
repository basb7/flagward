'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Spinner } from '@/components/ui/spinner';
import { ApiError, authApi } from '@/lib/api';
import { errorCopy } from '@/lib/error-copy';

const MIN_PASSWORD_LENGTH = 8;

/**
 * Maps the three distinguishable token failures to copy a person can act
 * on. Every other failure (missing fields, password policy rejections) is
 * handled separately by the caller -- this only covers the
 * status/bare-code pairs that mean the link itself is dead.
 */
function describePasswordResetConfirmError(
  status: number,
  message: string,
): string | null {
  if (status === 404 && message === 'token_not_found') {
    return 'This password reset link is invalid.';
  }
  if (status === 409 && message === 'token_already_used') {
    return 'This password reset link has already been used.';
  }
  if (status === 410 && message === 'token_expired') {
    return 'This password reset link has expired.';
  }
  return null;
}

type LinkState = { status: 'form' } | { status: 'invalid'; message: string };

export default function ResetPasswordPage() {
  const { token } = useParams<{ token: string }>();

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const [linkState, setLinkState] = useState<LinkState>({ status: 'form' });

  const passwordsMismatch =
    confirmPassword.length > 0 && confirmPassword !== password;
  const canSubmit =
    password.length >= MIN_PASSWORD_LENGTH && confirmPassword === password;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setPasswordError('');
    setIsLoading(true);

    try {
      await authApi.passwordResetConfirm(token, password);
      setIsDone(true);
    } catch (err) {
      if (err instanceof ApiError) {
        const linkErrorMessage = describePasswordResetConfirmError(
          err.status,
          err.message,
        );
        if (linkErrorMessage) {
          setLinkState({ status: 'invalid', message: linkErrorMessage });
        } else if (/^password:\s*/.test(err.message)) {
          // A password-policy rejection (`{"password": [...]}`), joined by
          // `request` as "password: msg1, msg2" -- strip the field name
          // since only one field can ever be present here.
          setPasswordError(err.message.replace(/^password:\s*/, ''));
        } else {
          // Anything else is the generic 400, e.g. "Token and password are
          // required" -- already a full sentence, shown as-is.
          setError(errorCopy(err.message));
        }
      } else {
        setError('Failed to reset the password.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  if (linkState.status === 'invalid') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background px-4">
        <Card className="w-full max-w-md">
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl font-bold text-center text-foreground">
              Link not valid
            </CardTitle>
            <CardDescription className="text-center text-muted-foreground">
              {linkState.message}
            </CardDescription>
          </CardHeader>
          <CardFooter className="flex flex-col gap-3 pt-4">
            <Link
              href="/forgot-password"
              className="text-center text-sm text-foreground underline-offset-4 hover:underline"
            >
              Request a new reset link
            </Link>
          </CardFooter>
        </Card>
      </div>
    );
  }

  if (isDone) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background px-4">
        <Card className="w-full max-w-md">
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl font-bold text-center text-foreground">
              Password reset
            </CardTitle>
            <CardDescription className="text-center text-muted-foreground">
              Your password has been reset.
            </CardDescription>
          </CardHeader>
          <CardFooter className="flex flex-col gap-3 pt-4">
            <Link href="/login" className="w-full">
              <Button className="w-full">Sign in</Button>
            </Link>
          </CardFooter>
        </Card>
      </div>
    );
  }

  const passwordErrorItems = passwordError ? passwordError.split(', ') : [];

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-bold text-center text-foreground">
            Choose a new password
          </CardTitle>
          <CardDescription className="text-center text-muted-foreground">
            Enter a new password for your account
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4 pb-6">
            {error && (
              <div
                role="alert"
                className="p-3 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-md"
              >
                {error}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="password" className="text-muted-foreground">
                New password
              </Label>
              <Input
                id="password"
                type="password"
                aria-describedby="password-hint"
                placeholder="Choose a new password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              {/*
                States what the client can predict up front. The server
                checks more -- similarity to the username and an exact
                common-password list -- and those come back as a server
                error rather than being guessed here.
              */}
              <p id="password-hint" className="text-xs text-muted-foreground">
                At least {MIN_PASSWORD_LENGTH} characters. Avoid common or
                all-numeric passwords.
              </p>
              {passwordErrorItems.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-4 text-xs text-destructive">
                  {passwordErrorItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="space-y-2">
              <Label
                htmlFor="confirm-password"
                className="text-muted-foreground"
              >
                Confirm password
              </Label>
              <Input
                id="confirm-password"
                type="password"
                placeholder="Re-enter the new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
              {passwordsMismatch && (
                <p className="text-xs text-destructive">
                  Passwords do not match.
                </p>
              )}
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3 pt-4">
            <Button
              type="submit"
              className="w-full"
              disabled={isLoading || !canSubmit}
            >
              {isLoading ? <Spinner size="sm" className="mr-2" /> : null}
              Reset password
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
