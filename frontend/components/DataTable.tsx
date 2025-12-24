"use client";

import { TableConfig, DataPayload } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";

interface DataTableProps {
  config: TableConfig;
  payload?: DataPayload;
}

export function DataTable({ config, payload }: DataTableProps) {
  // Extract table data from payload
  const refParts = config.dataset_ref.split(".");
  const tableName = refParts[1];

  let rows: Record<string, unknown>[] = [];

  if (payload?.tables) {
    const tableData = payload.tables.find((t) => t.name === tableName);
    if (tableData) {
      rows = tableData.rows;
    }
  }

  // Fallback: check if data is in raw format
  if (rows.length === 0 && Array.isArray(payload)) {
    rows = payload as Record<string, unknown>[];
  }

  const displayRows = rows.slice(0, config.max_rows);

  const formatCell = (value: unknown, column: string): string => {
    if (value === null || value === undefined) return "-";

    // Format currency columns
    if (
      column.toLowerCase().includes("monto") ||
      column.toLowerCase().includes("price") ||
      column.toLowerCase().includes("amount") ||
      column.toLowerCase().includes("value")
    ) {
      const num = Number(value);
      if (!isNaN(num)) return formatCurrency(num);
    }

    // Truncate long strings
    const str = String(value);
    if (str.length > 40) return str.slice(0, 40) + "...";

    return str;
  };

  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-700/50">
        <h3 className="text-lg font-semibold text-white">{config.title}</h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700/50 bg-gray-800/50">
              {config.columns.map((col) => (
                <th
                  key={col}
                  className="text-left px-4 py-3 text-gray-400 font-medium uppercase text-xs tracking-wider"
                >
                  {col.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700/30">
            {displayRows.length > 0 ? (
              displayRows.map((row, idx) => (
                <tr key={idx} className="hover:bg-gray-700/20 transition-colors">
                  {config.columns.map((col) => (
                    <td key={col} className="px-4 py-3 text-gray-300">
                      {formatCell(row[col], col)}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td
                  colSpan={config.columns.length}
                  className="px-4 py-8 text-center text-gray-500"
                >
                  No hay datos disponibles
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {rows.length > config.max_rows && (
        <div className="px-4 py-2 border-t border-gray-700/50 text-gray-500 text-sm text-center">
          Mostrando {displayRows.length} de {rows.length} filas
        </div>
      )}
    </div>
  );
}
