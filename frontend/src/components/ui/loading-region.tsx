'use client';

import { useTranslations } from 'next-intl';
import type * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * Wraps a group of decorative `Skeleton` blocks with the one accessible
 * announcement they collectively need. Individual skeletons stay
 * `aria-hidden`; a screen reader hears the announcement once from this region
 * rather than once per block.
 *
 * Pass `label` whenever a page can have more than one of these on screen at
 * the same time. Several regions all announcing the same generic "Loading
 * content" tell a screen reader user that three things are loading but not
 * which three, which is barely better than the unlabelled blocks this
 * component exists to replace. The label is already-translated text, because
 * what is loading is the calling page's knowledge, not this component's.
 */
function LoadingRegion({
  className,
  children,
  label,
  ...props
}: React.ComponentProps<'div'> & { label?: string }) {
  const t = useTranslations('skeleton');

  return (
    <div
      role="status"
      aria-label={label ?? t('loading')}
      className={cn(className)}
      {...props}
    >
      {children}
    </div>
  );
}

export { LoadingRegion };
