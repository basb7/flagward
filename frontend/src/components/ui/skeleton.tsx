import type * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * Shimmering placeholder block. Purely decorative -- it is always
 * `aria-hidden`, because the announcement that content is loading belongs to
 * the container wrapping a group of these (see `LoadingRegion`), never to
 * each individual block. `motion-safe:animate-pulse` keeps the pulse off for
 * anyone who has asked their system to reduce motion.
 */
function Skeleton({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      aria-hidden="true"
      className={cn('motion-safe:animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  );
}

export { Skeleton };
