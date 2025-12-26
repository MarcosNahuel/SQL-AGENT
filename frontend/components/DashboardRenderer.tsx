"use client";

import { motion } from "framer-motion";
import { DashboardSpec, DataPayload, ChartConfig, TableConfig, ComparisonChartConfig } from "@/lib/types";
import { KpiCard } from "./KpiCard";
import { ChartRenderer } from "./ChartRenderer";
import { ComparisonChart } from "./ComparisonChart";
import { DataTable } from "./DataTable";
import { NarrativePanel } from "./NarrativePanel";
import { BarChart3, TrendingUp, Sparkles, ArrowLeftRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface DashboardRendererProps {
  spec: DashboardSpec;
  payload?: DataPayload;
}

// Animation variants for staggered children
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.4,
      ease: [0.25, 0.46, 0.45, 0.94],
    },
  },
};

export function DashboardRenderer({ spec, payload }: DashboardRendererProps) {
  const { slots } = spec;

  // Separate comparison charts from regular charts and tables
  const comparisonCharts = (slots.charts || []).filter(
    (c): c is ComparisonChartConfig => c.type === "comparison_bar" || c.type === "comparison_kpi"
  );
  const charts = (slots.charts || []).filter(
    (c): c is ChartConfig => c.type !== "table" && c.type !== "comparison_bar" && c.type !== "comparison_kpi"
  );
  const tables = (slots.charts || []).filter((c): c is TableConfig => c.type === "table");

  // Categorize charts by type for intelligent placement
  const trendCharts = charts.filter(
    (c) => c.type === "line_chart" || c.type === "area_chart"
  );
  const barCharts = charts.filter((c) => c.type === "bar_chart");
  const pieCharts = charts.filter((c) => c.type === "pie_chart");

  // Check if we have comparison data
  const hasComparison = payload?.comparison?.is_comparison;

  // Calculate importance score for KPIs (higher value = more important)
  const sortedKpis = slots.series
    ? [...slots.series].sort((a, b) => {
        const priorityOrder = ["total_sales", "total_orders", "avg_order_value", "total_units"];
        const aIndex = priorityOrder.findIndex((p) => a.value_ref.includes(p));
        const bIndex = priorityOrder.findIndex((p) => b.value_ref.includes(p));
        return (aIndex === -1 ? 999 : aIndex) - (bIndex === -1 ? 999 : bIndex);
      })
    : [];

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-6"
    >
      {/* Header with Conclusion - Compact */}
      <motion.div variants={itemVariants} className="mb-4">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-4 h-4 text-accent-blue" />
          <h1 className="text-lg font-bold text-text-primary tracking-tight">
            {spec.title}
          </h1>
          {spec.subtitle && (
            <span className="text-text-muted text-sm">- {spec.subtitle}</span>
          )}
        </div>

        {spec.conclusion && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2, duration: 0.3 }}
            className="px-3 py-2 glass-card text-sm"
            style={{
              background:
                "linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(139, 92, 246, 0.05))",
            }}
          >
            <p className="text-accent-blue font-medium">{spec.conclusion}</p>
          </motion.div>
        )}
      </motion.div>

      {/* KPI Row - Compact single row */}
      {sortedKpis.length > 0 && (
        <motion.div variants={itemVariants}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {sortedKpis.map((kpi, idx) => (
              <KpiCard key={idx} config={kpi} payload={payload} index={idx} />
            ))}
          </div>
        </motion.div>
      )}

      {/* Comparison Charts - Full width when present */}
      {comparisonCharts.length > 0 && hasComparison && (
        <motion.div variants={itemVariants} className="space-y-3">
          {/* Section Header */}
          <div className="flex items-center gap-2">
            <ArrowLeftRight className="w-4 h-4 text-accent-emerald" />
            <h3 className="text-sm font-semibold text-text-primary">
              Comparativa de Periodos
            </h3>
          </div>

          {/* Comparison Chart - Full Width */}
          <div className="grid grid-cols-1 gap-4">
            {comparisonCharts.map((chart, idx) => (
              <motion.div key={`comparison-${idx}`} variants={itemVariants}>
                <ComparisonChart
                  config={chart}
                  comparison={payload?.comparison}
                  index={idx}
                />
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Charts Grid - Compact */}
      {charts.length > 0 && (
        <motion.div variants={itemVariants} className="space-y-3">
          {/* Section Header */}
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-accent-blue" />
            <h3 className="text-sm font-semibold text-text-primary">
              Visualizaciones
            </h3>
            <span className="text-xs text-text-muted">
              ({charts.length})
            </span>
          </div>

          {/* Bento Grid for Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Trend Chart (Line/Area) - Left, full height if bar chart exists */}
            {trendCharts.length > 0 && (
              <motion.div
                variants={itemVariants}
                className={cn(
                  "relative",
                  barCharts.length > 0 && "lg:row-span-1"
                )}
              >
                {/* Type badge */}
                <div className="absolute -top-2 left-4 z-20 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-blue/20 text-accent-blue flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  Tendencia
                </div>
                <ChartRenderer
                  config={trendCharts[0]}
                  payload={payload}
                  index={0}
                />
              </motion.div>
            )}

            {/* Bar Chart - Right */}
            {barCharts.length > 0 && (
              <motion.div variants={itemVariants} className="relative">
                <div className="absolute -top-2 left-4 z-20 px-2 py-0.5 rounded-full text-xs font-medium bg-accent-emerald/20 text-accent-emerald flex items-center gap-1">
                  <BarChart3 className="w-3 h-3" />
                  Comparativo
                </div>
                <ChartRenderer
                  config={barCharts[0]}
                  payload={payload}
                  index={1}
                />
              </motion.div>
            )}

            {/* Handle edge cases */}
            {trendCharts.length === 0 && barCharts.length > 1 && (
              <motion.div variants={itemVariants}>
                <ChartRenderer
                  config={barCharts[1]}
                  payload={payload}
                  index={2}
                />
              </motion.div>
            )}

            {barCharts.length === 0 && trendCharts.length > 1 && (
              <motion.div variants={itemVariants}>
                <ChartRenderer
                  config={trendCharts[1]}
                  payload={payload}
                  index={2}
                />
              </motion.div>
            )}
          </div>

          {/* Additional charts in a new row */}
          {charts.length > 2 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {charts.slice(2).map((chart, idx) => (
                <motion.div key={idx + 2} variants={itemVariants}>
                  <ChartRenderer
                    config={chart}
                    payload={payload}
                    index={idx + 2}
                  />
                </motion.div>
              ))}
            </div>
          )}

          {/* Pie charts get their own section if present */}
          {pieCharts.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {pieCharts.map((chart, idx) => (
                <motion.div key={`pie-${idx}`} variants={itemVariants}>
                  <ChartRenderer
                    config={chart}
                    payload={payload}
                    index={charts.indexOf(chart)}
                  />
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {/* Narrative/Insights Section */}
      {slots.narrative && slots.narrative.length > 0 && (
        <motion.div variants={itemVariants}>
          <NarrativePanel narratives={slots.narrative} />
        </motion.div>
      )}

      {/* Tables */}
      {tables.length > 0 && (
        <motion.div variants={itemVariants} className="space-y-4">
          {tables.map((table, idx) => (
            <DataTable key={idx} config={table} payload={payload} />
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}
