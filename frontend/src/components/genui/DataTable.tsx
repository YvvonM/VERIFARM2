// GenUI Table — renders the backend `Table` componentType.
// Props contract (app/models/ui_schemas.py::TableProps):
//   { columns: string[], rows: unknown[][], caption?: string | null }

export interface DataTableProps {
  columns: string[];
  rows: Array<Array<unknown>>;
  caption?: string | null;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function DataTable({ columns, rows, caption }: DataTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className="border-b border-gray-300 px-3 py-2 text-left font-semibold text-gray-700"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={Math.max(columns.length, 1)}
                className="px-3 py-4 text-center text-gray-400"
              >
                No matching data.
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i} className="odd:bg-white even:bg-gray-50">
                {row.map((value, j) => (
                  <td
                    key={j}
                    className="border-b border-gray-100 px-3 py-2 text-gray-800"
                  >
                    {formatCell(value)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
      {caption ? <p className="mt-2 text-xs text-gray-500">{caption}</p> : null}
    </div>
  );
}

export default DataTable;
