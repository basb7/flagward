'use client';

import { FloatingLanguageSwitcher } from '@/components/ui/floating-language-switcher';
import { AuthProvider } from '@/lib/auth-context';

export default function InviteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      {children}
      <FloatingLanguageSwitcher />
    </AuthProvider>
  );
}
