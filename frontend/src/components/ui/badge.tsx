import { cva, type VariantProps } from 'class-variance-authority';
import type * as React from 'react';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
  {
    variants: {
      variant: {
        default: 'border-border bg-muted text-foreground',
        muted: 'border-border bg-transparent text-muted-foreground',
        success: 'border-success/25 bg-success/10 text-success',
        warning: 'border-warning/25 bg-warning/10 text-warning',
        danger: 'border-destructive/25 bg-destructive/10 text-destructive',
        info: 'border-info/25 bg-info/10 text-info',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return (
    <span
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  );
}

const dotVariants = cva('inline-block size-1.5 shrink-0 rounded-full', {
  variants: {
    tone: {
      success: 'bg-success',
      warning: 'bg-warning',
      danger: 'bg-destructive',
      info: 'bg-info',
      muted: 'bg-muted-foreground',
    },
  },
  defaultVariants: {
    tone: 'muted',
  },
});

/** Small status dot, for "active / stale" style indicators in dense tables. */
function StatusDot({
  className,
  tone,
  pulse = false,
  ...props
}: React.ComponentProps<'span'> &
  VariantProps<typeof dotVariants> & { pulse?: boolean }) {
  return (
    <span
      data-slot="status-dot"
      className={cn(dotVariants({ tone }), pulse && 'animate-pulse', className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants, StatusDot };
