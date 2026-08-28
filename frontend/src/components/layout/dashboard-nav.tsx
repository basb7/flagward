'use client';

import { Activity, Flag, Layers, LayoutGrid, LogOut, User } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAuth } from '@/lib/auth-context';
import { cn } from '@/lib/utils';

const TABS = [
  { href: '/dashboard', label: 'Overview', icon: LayoutGrid, exact: true },
  { href: '/dashboard/flags', label: 'Flags', icon: Flag },
  { href: '/dashboard/environments', label: 'Environments', icon: Layers },
  { href: '/dashboard/monitoring', label: 'Monitoring', icon: Activity },
] as const;

export function DashboardNav() {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  const isActive = (tab: (typeof TABS)[number]) =>
    'exact' in tab && tab.exact
      ? pathname === tab.href
      : pathname.startsWith(tab.href);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between gap-4">
          <Link href="/dashboard" className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-md bg-foreground text-background">
              <Flag className="size-3.5" />
            </span>
            <span className="font-heading text-sm font-semibold tracking-tight">
              Flagward
            </span>
          </Link>

          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-2 text-muted-foreground hover:text-foreground"
                />
              }
            >
              <User className="size-4" />
              <span className="max-w-32 truncate">{user?.username}</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={logout} className="text-destructive">
                <LogOut className="mr-2 size-4" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <nav
          aria-label="Dashboard sections"
          className="-mb-px flex gap-1 overflow-x-auto"
        >
          {TABS.map((tab) => {
            const active = isActive(tab);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex items-center gap-1.5 border-b-2 px-3 pb-2.5 text-sm whitespace-nowrap transition-colors',
                  active
                    ? 'border-foreground text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                <tab.icon className="size-4" />
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
