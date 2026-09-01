'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
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
import { authApi } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { safeNextPath } from '@/lib/utils';

// Next.js 16 requires a `<Suspense>` boundary around any Client Component
// that calls `useSearchParams`, or the production build fails (see
// node_modules/next/dist/docs/.../use-search-params.md). The form is split
// out so the Suspense boundary wraps only the part that needs it.
function LoginForm() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  // Defaults to hidden until the config check resolves true, so the link
  // never flashes in and then disappears. A failed background check is
  // treated the same as disabled -- it never surfaces as an error here.
  const [passwordResetEnabled, setPasswordResetEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    authApi
      .getConfig()
      .then((config) => {
        if (!cancelled) setPasswordResetEnabled(config.password_reset_enabled);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Only a same-origin, path-rooted `next` is ever honoured -- see
  // `safeNextPath` for what's rejected and why (open-redirect prevention).
  const rawNext = searchParams.get('next');
  const next = safeNextPath(rawNext);
  const registerHref = rawNext
    ? `/register?next=${encodeURIComponent(next)}`
    : '/register';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login(username, password);
      router.push(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-bold text-center text-foreground">
            Flagward
          </CardTitle>
          <CardDescription className="text-center text-muted-foreground">
            Enter your credentials to access the dashboard
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
              <Label htmlFor="username" className="text-muted-foreground">
                Username
              </Label>
              <Input
                id="username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-muted-foreground">
                  Password
                </Label>
                {passwordResetEnabled && (
                  <Link
                    href="/forgot-password"
                    className="text-xs text-foreground underline-offset-4 hover:underline"
                  >
                    Forgot password?
                  </Link>
                )}
              </div>
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3 pt-4">
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? 'Signing in...' : 'Sign in'}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              Don&apos;t have an account?{' '}
              <Link
                href={registerHref}
                className="text-foreground underline-offset-4 hover:underline"
              >
                Create one
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}

function LoginFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Spinner size="lg" />
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginFallback />}>
      <LoginForm />
    </Suspense>
  );
}
