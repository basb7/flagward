import type { LucideIcon } from 'lucide-react';
import Link from 'next/link';
import type * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * Single metric tile: label on top, the number large, one line of context below.
 * Renders as a link when `href` is given, otherwise as a plain panel.
 */
function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  href,
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: LucideIcon;
  href?: string;
  className?: string;
}) {
  const body = (
    <div
      className={cn(
        'flex h-full flex-col justify-between gap-4 rounded-xl border border-border bg-card p-4 transition-colors',
        href && 'hover:border-muted-foreground/40',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium text-muted-foreground">
          {label}
        </span>
        {Icon ? (
          <Icon className="size-4 shrink-0 text-muted-foreground" />
        ) : null}
      </div>
      <div className="space-y-1">
        <div className="font-heading text-3xl leading-none font-semibold tracking-tight text-foreground tabular-nums">
          {value}
        </div>
        {hint ? (
          <div className="text-xs text-muted-foreground">{hint}</div>
        ) : null}
      </div>
    </div>
  );

  if (!href) {
    return body;
  }

  return (
    <Link href={href} className="block h-full">
      {body}
    </Link>
  );
}

export { StatCard };
