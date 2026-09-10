'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { PageHeaderSkeleton } from '@/components/dashboard/skeletons/page-header-skeleton';
import { DashboardNav } from '@/components/layout/dashboard-nav';
import { LoadingRegion } from '@/components/ui/loading-region';
import { Skeleton } from '@/components/ui/skeleton';
import { AuthProvider, useAuth } from '@/lib/auth-context';
import { TenantProvider } from '@/lib/tenant-context';

function DashboardContent({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    // Which of the dashboard's tabs is loading is not known yet -- the one
    // shape every one of them shares is a `PageHeader` followed by content,
    // so that is all this mirrors rather than guessing a specific page.
    return (
      <div className="min-h-screen bg-background">
        <div className="h-16 border-b border-border" />
        <LoadingRegion className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
          <PageHeaderSkeleton />
          <Skeleton className="h-48 w-full" />
        </LoadingRegion>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <DashboardNav />
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <TenantProvider>
        <DashboardContent>{children}</DashboardContent>
      </TenantProvider>
    </AuthProvider>
  );
}
