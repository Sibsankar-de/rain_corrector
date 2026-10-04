/** Small labelled table used for tabular readouts. */

import type { ReactNode } from "react";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  width?: string;
  render: (row: T, index: number) => ReactNode;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  caption?: string;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  dense?: boolean;
}

const ALIGN: Record<NonNullable<DataTableColumn<unknown>["align"]>, string> = {
  left: "text-left",
  right: "text-right",
  center: "text-center"
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  onRowClick,
  emptyMessage = "No rows to display",
  dense = false
}: DataTableProps<T>) {
  return (
    <div className="scrollbar-thin overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr className="border-b border-edge">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={`data-label ${ALIGN[column.align ?? "left"]} whitespace-nowrap px-4 py-2.5 font-medium`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-10 text-center text-sm text-ink-muted"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr
                key={rowKey(row, index)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={`border-b border-edge last:border-0 ${onRowClick ? "cursor-pointer hover:bg-surface-sunken" : ""}`}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={`${ALIGN[column.align ?? "left"]} px-4 ${dense ? "py-1.5" : "py-2.5"} align-middle`}
                  >
                    {column.render(row, index)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
