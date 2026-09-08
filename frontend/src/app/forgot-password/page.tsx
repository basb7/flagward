'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
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

export default function ForgotPasswordPage() {
  const t = useTranslations('forgotPassword');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // Set only once the request call resolves without throwing -- see the
  // fixed confirmation copy below, which never depends on whether the
  // account exists or on what `detail` text the backend happens to return.
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await authApi.passwordResetRequest(email);
      setSubmittedEmail(email);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setError(t('rateLimitError'));
        } else {
          // A 400 here is a DRF field error (`{"email": [...]}`), which
          // `request` joins as "email: msg1, msg2" -- strip the field name
          // for cleaner display since only one field can ever be present.
          setError(err.message.replace(/^email:\s*/, ''));
        }
      } else {
        setError(t('genericError'));
      }
    } finally {
      setIsLoading(false);
    }
  };

  if (submittedEmail) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="w-full max-w-md">
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl font-bold text-center text-foreground">
              {t('checkInboxTitle')}
            </CardTitle>
            <CardDescription className="text-center text-muted-foreground">
              {t.rich('checkInboxDescription', {
                email: submittedEmail,
                strong: (chunks) => (
                  <strong className="text-foreground">{chunks}</strong>
                ),
              })}
            </CardDescription>
          </CardHeader>
          <CardFooter className="flex flex-col gap-3 pt-4">
            <Link
              href="/login"
              className="text-center text-sm text-foreground underline-offset-4 hover:underline"
            >
              {t('backToSignIn')}
            </Link>
          </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-bold text-center text-foreground">
            {t('title')}
          </CardTitle>
          <CardDescription className="text-center text-muted-foreground">
            {t('description')}
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
              <Label htmlFor="email" className="text-muted-foreground">
                {t('emailLabel')}
              </Label>
              <Input
                id="email"
                type="email"
                placeholder={t('emailPlaceholder')}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3 pt-4">
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? <Spinner size="sm" className="mr-2" /> : null}
              {t('submit')}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              {t('rememberedPassword')}{' '}
              <Link
                href="/login"
                className="text-foreground underline-offset-4 hover:underline"
              >
                {t('signIn')}
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
