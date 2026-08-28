'use client';

import { Switch as SwitchPrimitive } from '@base-ui/react/switch';
import type * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * On/off control.
 *
 * The track keeps a visible border in both states — an unchecked track painted
 * only in `bg-muted` disappears into a dark card and stops reading as a control.
 * State is carried by thumb position, track color AND the caller's label, never
 * by color alone.
 */
function Switch({
  className,
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border p-0.5 transition-colors outline-none',
        'border-border bg-muted',
        'data-checked:border-success data-checked:bg-success',
        'focus-visible:ring-3 focus-visible:ring-ring/50',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="size-4 rounded-full bg-foreground shadow-sm transition-transform data-checked:translate-x-4 data-unchecked:translate-x-0"
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
