import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

/**
 * Placeholder for a row of `StatCard`s. Every dashboard page that leads with
 * a stat-card grid uses this instead of a bespoke skeleton per page, so the
 * shape only needs to be gotten right once; only the count and grid columns
 * (via `className`) vary between pages.
 */
function StatCardsSkeleton({
  count,
  className,
}: {
  count: number;
  className?: string;
}) {
  return (
    <div className={cn('grid gap-4 sm:grid-cols-2 lg:grid-cols-4', className)}>
      {Array.from({ length: count }, (_, index) => (
        <div
          // biome-ignore lint/suspicious/noArrayIndexKey: a fixed-length list of interchangeable placeholders, never reordered or filtered.
          key={index}
          data-slot="stat-card-skeleton"
          className="flex h-full flex-col justify-between gap-4 rounded-xl border border-border bg-card p-4"
        >
          <div className="flex items-start justify-between gap-2">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="size-4 shrink-0" />
          </div>
          <div className="space-y-2">
            <Skeleton className="h-7 w-16" />
            <Skeleton className="h-3 w-24" />
          </div>
        </div>
      ))}
    </div>
  );
}

export { StatCardsSkeleton };
