'use client';

import { useId, useState } from 'react';

import type { EvaluationBucket } from '@/lib/api';
import { cn } from '@/lib/utils';

const SERIES = [
  { key: 'true_count', label: 'Served true', className: 'bg-viz-true' },
  { key: 'false_count', label: 'Served false', className: 'bg-viz-false' },
] as const;

function formatHour(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDayHour(timestamp: string) {
  return new Date(timestamp).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Hourly evaluation volume as stacked bars: true at the baseline, false above.
 *
 * Series colors come from the validated `--viz-true` / `--viz-false` pair. The
 * legend is always rendered, so the two series are never distinguished by color
 * alone, and the same numbers are exposed as a screen-reader table.
 */
export function EvaluationsChart({
  buckets,
  className,
}: {
  buckets: EvaluationBucket[];
  className?: string;
}) {
  const tableId = useId();
  const [hovered, setHovered] = useState<number | null>(null);
  const maxTotal = Math.max(...buckets.map((bucket) => bucket.total), 1);

  // Label only the ends and the midpoint — one label per bar collides at 24 bars.
  const labelledIndexes = new Set(
    buckets.length > 2
      ? [0, Math.floor((buckets.length - 1) / 2), buckets.length - 1]
      : buckets.map((_, index) => index),
  );

  const active = hovered === null ? null : buckets[hovered];
  const activeOffset =
    hovered === null ? 0 : ((hovered + 0.5) / buckets.length) * 100;

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {SERIES.map((series) => (
          <span
            key={series.key}
            className="flex items-center gap-1.5 text-xs text-muted-foreground"
          >
            <span
              className={cn('size-2 shrink-0 rounded-sm', series.className)}
            />
            {series.label}
          </span>
        ))}
      </div>

      <div className="relative">
        {active ? (
          <div
            className="pointer-events-none absolute -top-1 z-10 -translate-x-1/2 -translate-y-full rounded-lg border border-border bg-popover px-2.5 py-2 text-xs whitespace-nowrap shadow-lg"
            style={{ left: `${activeOffset}%` }}
          >
            <div className="font-medium text-foreground">
              {formatDayHour(active.timestamp)}
            </div>
            <div className="mt-1 space-y-0.5 text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <span className="size-2 shrink-0 rounded-sm bg-viz-true" />
                Served true
                <span className="ml-auto pl-3 text-foreground tabular-nums">
                  {active.true_count}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="size-2 shrink-0 rounded-sm bg-viz-false" />
                Served false
                <span className="ml-auto pl-3 text-foreground tabular-nums">
                  {active.false_count}
                </span>
              </div>
            </div>
          </div>
        ) : null}

        <div
          className="flex h-40 items-end gap-[2px]"
          aria-describedby={tableId}
        >
          {buckets.map((bucket, index) => (
            <button
              key={bucket.timestamp}
              type="button"
              // The column is the hit target, not the bar: an empty hour is
              // still hoverable and short bars stay easy to reach.
              className="group/bar flex h-full flex-1 cursor-default flex-col justify-end gap-[2px] rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(index)}
              onBlur={() => setHovered(null)}
              aria-label={`${formatDayHour(bucket.timestamp)}: ${bucket.true_count} true, ${bucket.false_count} false`}
            >
              {bucket.total === 0 ? (
                <span className="h-px w-full rounded-full bg-border" />
              ) : (
                <>
                  {bucket.false_count > 0 ? (
                    <span
                      className="w-full rounded-t-[4px] bg-viz-false transition-opacity group-hover/bar:opacity-80"
                      style={{
                        height: `${(bucket.false_count / maxTotal) * 100}%`,
                        minHeight: '2px',
                      }}
                    />
                  ) : null}
                  {bucket.true_count > 0 ? (
                    <span
                      className={cn(
                        'w-full bg-viz-true transition-opacity group-hover/bar:opacity-80',
                        bucket.false_count === 0 && 'rounded-t-[4px]',
                      )}
                      style={{
                        height: `${(bucket.true_count / maxTotal) * 100}%`,
                        minHeight: '2px',
                      }}
                    />
                  ) : null}
                </>
              )}
            </button>
          ))}
        </div>

        <div className="mt-2 flex gap-[2px]">
          {buckets.map((bucket, index) => (
            <span
              key={bucket.timestamp}
              className="flex-1 text-center text-[11px] text-muted-foreground"
            >
              {labelledIndexes.has(index) ? formatHour(bucket.timestamp) : ' '}
            </span>
          ))}
        </div>
      </div>

      <table id={tableId} className="sr-only">
        <caption>Evaluations per hour</caption>
        <thead>
          <tr>
            <th>Hour</th>
            <th>Served true</th>
            <th>Served false</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((bucket) => (
            <tr key={bucket.timestamp}>
              <td>{formatDayHour(bucket.timestamp)}</td>
              <td>{bucket.true_count}</td>
              <td>{bucket.false_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
