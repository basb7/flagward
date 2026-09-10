import { Skeleton } from '@/components/ui/skeleton';

/**
 * Placeholder for the `PageHeader` title/description rhythm. `withBackButton`
 * covers the one page (rules) whose header sits beside a back button rather
 * than alone.
 */
function PageHeaderSkeleton({
  withBackButton = false,
}: {
  withBackButton?: boolean;
}) {
  const header = (
    <div className="space-y-3">
      <Skeleton data-slot="page-header-title-skeleton" className="h-8 w-48" />
      <Skeleton
        data-slot="page-header-description-skeleton"
        className="h-4 w-72"
      />
    </div>
  );

  if (!withBackButton) {
    return header;
  }

  return (
    <div className="flex items-start gap-3">
      <Skeleton
        data-slot="page-header-back-skeleton"
        className="mt-1 size-9 shrink-0 rounded-md"
      />
      <div className="flex-1">{header}</div>
    </div>
  );
}

export { PageHeaderSkeleton };
