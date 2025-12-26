"use client";

import { TableConfig, DataPayload } from "@/lib/types";
import { formatCurrency } from "@/lib/utils";
import { Download, ExternalLink } from "lucide-react";

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

  // Generate CSV content for download
  const generateCSV = (): string => {
    if (rows.length === 0) return "";

    const headers = config.columns.join(",");
    const csvRows = rows.map(row =>
      config.columns.map(col => {
        const value = row[col];
        if (value === null || value === undefined) return "";
        const str = String(value);
        // Escape commas and quotes
        if (str.includes(",") || str.includes('"') || str.includes("\n")) {
          return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
      }).join(",")
    );

    return [headers, ...csvRows].join("\n");
  };

  // Download as CSV (Excel compatible)
  const handleDownload = () => {
    const csv = generateCSV();
    if (!csv) return;

    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${tableName || "datos"}_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Open full table in new window
  const handleOpenFullTable = () => {
    if (rows.length === 0) return;

    const newWindow = window.open("", "_blank", "width=1200,height=800");
    if (!newWindow) return;

    const tableHTML = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>${config.title} - Datos Completos</title>
        <style>
          body { font-family: system-ui, -apple-system, sans-serif; padding: 20px; background: #1a1a2e; color: #e0e0e0; }
          h1 { color: #60a5fa; margin-bottom: 10px; }
          .info { color: #9ca3af; margin-bottom: 20px; }
          table { border-collapse: collapse; width: 100%; background: #242442; }
          th { background: #2d2d5a; color: #60a5fa; text-align: left; padding: 12px; border-bottom: 2px solid #3b3b6d; }
          td { padding: 10px 12px; border-bottom: 1px solid #3b3b6d; }
          tr:hover { background: #2d2d5a; }
          .btn { background: #3b82f6; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; margin-right: 10px; }
          .btn:hover { background: #2563eb; }
          .actions { margin-bottom: 20px; }
        </style>
      </head>
      <body>
        <h1>${config.title}</h1>
        <p class="info">${rows.length} registros</p>
        <div class="actions">
          <button class="btn" onclick="downloadCSV()">Descargar CSV</button>
        </div>
        <table>
          <thead>
            <tr>
              ${config.columns.map(col => `<th>${col.replace(/_/g, " ").toUpperCase()}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                ${config.columns.map(col => `<td>${row[col] ?? "-"}</td>`).join("")}
              </tr>
            `).join("")}
          </tbody>
        </table>
        <script>
          function downloadCSV() {
            const data = ${JSON.stringify(rows)};
            const cols = ${JSON.stringify(config.columns)};
            const headers = cols.join(",");
            const csvRows = data.map(row =>
              cols.map(col => {
                const value = row[col];
                if (value === null || value === undefined) return "";
                const str = String(value);
                if (str.includes(",") || str.includes('"') || str.includes("\\n")) {
                  return '"' + str.replace(/"/g, '""') + '"';
                }
                return str;
              }).join(",")
            );
            const csv = [headers, ...csvRows].join("\\n");
            const blob = new Blob(["\\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "${tableName || "datos"}_${new Date().toISOString().slice(0,10)}.csv";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
          }
        </script>
      </body>
      </html>
    `;

    newWindow.document.write(tableHTML);
    newWindow.document.close();
  };

  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-700/50 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">{config.title}</h3>
        {rows.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-accent-blue hover:text-white bg-accent-blue/10 hover:bg-accent-blue/20 rounded-lg transition-colors"
              title="Descargar como CSV"
            >
              <Download className="w-3.5 h-3.5" />
              CSV
            </button>
            <button
              onClick={handleOpenFullTable}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-accent-emerald hover:text-white bg-accent-emerald/10 hover:bg-accent-emerald/20 rounded-lg transition-colors"
              title="Ver tabla completa"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Ver todo
            </button>
          </div>
        )}
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
