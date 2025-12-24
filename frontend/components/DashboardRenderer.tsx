"use client";

import { DashboardSpec, DataPayload, ChartConfig, TableConfig } from "@/lib/types";
import { KpiCard } from "./KpiCard";
import { ChartRenderer } from "./ChartRenderer";
import { DataTable } from "./DataTable";
import { NarrativePanel } from "./NarrativePanel";
import { BarChart3, TrendingUp } from "lucide-react";

interface DashboardRendererProps {
  spec: DashboardSpec;
  payload?: DataPayload;
}

export function DashboardRenderer({ spec, payload }: DashboardRendererProps) {
  const { slots } = spec;

  // Separate charts from tables
  const charts = slots.charts.filter((c): c is ChartConfig => c.type !== "table");
  const tables = slots.charts.filter((c): c is TableConfig => c.type === "table");

  // Ensure we have at least 2 charts by type
  const trendCharts = charts.filter(c => c.type === "line_chart" || c.type === "area_chart");
  const barCharts = charts.filter(c => c.type === "bar_chart");

  return (
    <div className="space-y-6">
      {/* Header with Conclusion */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">{spec.title}</h1>
        {spec.subtitle && (
          <p className="text-gray-400 mt-1">{spec.subtitle}</p>
        )}
        {spec.conclusion && (
          <div className="mt-3 px-4 py-3 bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/20 rounded-xl">
            <p className="text-blue-300 font-medium">{spec.conclusion}</p>
          </div>
        )}
      </div>

      {/* KPI Series - First for visibility */}
      {slots.series && slots.series.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {slots.series.map((kpi, idx) => (
            <KpiCard key={idx} config={kpi} payload={payload} />
          ))}
        </div>
      )}

      {/* Charts Grid - 2 columns for different chart types */}
      {charts.length > 0 && (
        <div className="space-y-4">
          {/* Section Header */}
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-blue-400" />
            <h3 className="text-lg font-semibold text-white">Visualizaciones</h3>
            <span className="text-sm text-gray-500">({charts.length} graficos)</span>
          </div>

          {/* Two charts side by side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Trend Chart (Line/Area) - Left */}
            {trendCharts.length > 0 && (
              <div className="relative">
                <div className="absolute -top-2 left-4 px-2 py-0.5 bg-blue-500/20 rounded text-xs text-blue-400 flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  Tendencia
                </div>
                <ChartRenderer config={trendCharts[0]} payload={payload} />
              </div>
            )}

            {/* Bar Chart - Right */}
            {barCharts.length > 0 && (
              <div className="relative">
                <div className="absolute -top-2 left-4 px-2 py-0.5 bg-green-500/20 rounded text-xs text-green-400 flex items-center gap-1">
                  <BarChart3 className="w-3 h-3" />
                  Comparativo
                </div>
                <ChartRenderer config={barCharts[0]} payload={payload} />
              </div>
            )}

            {/* If only one type exists, show remaining charts */}
            {trendCharts.length === 0 && barCharts.length > 1 && (
              <ChartRenderer config={barCharts[1]} payload={payload} />
            )}
            {barCharts.length === 0 && trendCharts.length > 1 && (
              <ChartRenderer config={trendCharts[1]} payload={payload} />
            )}
          </div>

          {/* Additional charts if more than 2 */}
          {charts.length > 2 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {charts.slice(2).map((chart, idx) => (
                <ChartRenderer key={idx + 2} config={chart} payload={payload} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Narrative/Insights Section */}
      {slots.narrative && slots.narrative.length > 0 && (
        <NarrativePanel narratives={slots.narrative} />
      )}

      {/* Tables */}
      {tables.length > 0 && (
        <div className="space-y-4">
          {tables.map((table, idx) => (
            <DataTable key={idx} config={table} payload={payload} />
          ))}
        </div>
      )}
    </div>
  );
}
