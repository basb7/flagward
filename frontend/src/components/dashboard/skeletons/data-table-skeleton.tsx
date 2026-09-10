import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

/**
 * Placeholder for a `Table` whose real header and row shapes are already
 * known before the data that fills them has arrived. Reused across every
 * dashboard table (monitoring, members, environments, flags, rules) instead
 * of one bespoke skeleton per page -- only `columns` and `rows` differ.
 */
function DataTableSkeleton({
  columns,
  rows = 5,
}: {
  columns: number;
  rows?: number;
}) {
  const columnIndexes = Array.from({ length: columns }, (_, index) => index);
  const rowIndexes = Array.from({ length: rows }, (_, index) => index);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {columnIndexes.map((column) => (
            <TableHead key={column}>
              <Skeleton className="h-4 w-16" />
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rowIndexes.map((row) => (
          <TableRow key={row}>
            {columnIndexes.map((column) => (
              <TableCell key={column}>
                <Skeleton className="h-4 w-full max-w-32" />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export { DataTableSkeleton };
