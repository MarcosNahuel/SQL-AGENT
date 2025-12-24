"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  TooltipProps,
} from "recharts";
import { ComparisonChartConfig, ComparisonData } from "@/lib/types";
import { formatCurrency, formatNumber, cn } from "@/lib/utils";

interface ComparisonChartProps {
  config: ComparisonChartConfig;
  comparison?: ComparisonData;
  index?: number;
}

const CHART_COLORS = {
  current: "#10b981",
  currentGlow: "rgba(16, 185, 129, 0.4)",
  previous: "#6366f1",
  previousGlow: "rgba(99, 102, 241, 0.4)",
  positive: "#10b981",
  negative: "#ff3366",
};

const METRIC_LABELS: Record<string, string> = {
  total_sales: "Ventas",
  total_orders: "Ordenes",
  avg_order_value: "Ticket Promedio",
  total_units: "Unidades",
};

const METRIC_FORMATS: Record<string, "currency" | "number"> = {
  total_sales: "currency",
  total_orders: "number",
  avg_order_value: "currency",
  total_units: "number",
};

function ComparisonTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || !payload.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-tooltip px-4 py-3 shadow-2xl"
    >
      <p className="text-text-subtle text-xs font-medium mb-2 uppercase tracking-wide">
        {label}
      </p>
      {payload.map((entry, index) => {
        const value = entry.value as number;
        const format = entry.dataKey === "current" || entry.dataKey === "previous" ? "currency" : "number";
        return (
          <div key={index} className="flex items-center gap-2 mb-1">
            <div
              className="w-3 h-3 rounded-sm"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-text-muted text-xs">{entry.name}:</span>
            <span className="text-text-primary font-semibold">
              {format === "currency" ? formatCurrency(value) : formatNumber(value)}
            </span>
          </div>
        );
      })}
      {payload.length === 2 && (
        <div className="mt-2 pt-2 border-t border-border-subtle">
          <div className="flex items-center gap-1 text-xs">
            <span className="text-text-muted">Diferencia:</span>
            {(() => {
              const current = payload.find(p => p.dataKey === "current")?.value as number || 0;
              const previous = payload.find(p => p.dataKey === "previous")?.value as number || 0;
              const delta = current - previous;
              const deltaPct = previous !== 0 ? ((delta / previous) * 100) : 0;
              const isPositive = delta > 0;
              return (
                <span className={cn(
                  "font-medium",
                  isPositive ? "text-accent-emerald" : "text-accent-neon-red"
                )}>
                  {isPositive ? "+" : ""}{deltaPct.toFixed(1)}%
                </span>
              );
            })()}
          </div>
        </div>
      )}
    </motion.div>
  );
}

export function ComparisonChart({ config, comparison, index = 0 }: ComparisonChartProps) {
  const data = useMemo(() => {
    if (!comparison) return [];

    return config.metrics.map(metric => {
      const currentValue = comparison.current_period.kpis?.[metric] ?? 0;
      const previousValue = comparison.previous_period.kpis?.[metric] ?? 0;
      const delta = currentValue - previousValue;
      const deltaPct = previousValue !== 0 ? ((delta / previousValue) * 100) : 0;

      return {
        name: METRIC_LABELS[metric] || metric,
        metric,
        current: currentValue,
        previous: previousValue,
        delta,
        deltaPct,
      };
    });
  }, [config.metrics, comparison]);

  if (data.length === 0 || !comparison) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: index * 0.1 }}
        className="chart-container p-6"
      >
        <h3 className="text-lg font-semibold text-text-primary mb-4">{config.title}</h3>
        <div className="h-48 flex items-center justify-center text-text-muted">
          <p>No hay datos de comparacion disponibles</p>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.15 }}
      className="chart-container p-4 relative overflow-hidden"
    >
      {/* Glow effect */}
      <div
        className="absolute -top-20 -right-20 w-40 h-40 rounded-full opacity-20 blur-3xl pointer-events-none"
        style={{ background: CHART_COLORS.currentGlow }}
      />

      <div className="flex items-center justify-between mb-4 relative z-10">
        <h3 className="text-sm font-semibold text-text-primary">{config.title}</h3>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: CHART_COLORS.current }} />
            <span className="text-text-muted">{config.current_label}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: CHART_COLORS.previous }} />
            <span className="text-text-muted">{config.previous_label}</span>
          </div>
        </div>
      </div>

      <div style={{ height: 260 }} className="relative z-10">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 10, right: 10, left: 10, bottom: 5 }}
            barCategoryGap="20%"
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.06)"
              vertical={false}
            />
            <XAxis
              dataKey="name"
              stroke="rgba(255,255,255,0.3)"
              fontSize={11}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              tick={{ fill: "rgba(255,255,255,0.6)" }}
            />
            <YAxis
              stroke="rgba(255,255,255,0.3)"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => {
                if (v >= 1000000) return `$${(v / 1000000).toFixed(1)}M`;
                if (v >= 1000) return `$${(v / 1000).toFixed(0)}k`;
                return formatNumber(v);
              }}
              tick={{ fill: "rgba(255,255,255,0.5)" }}
              width={70}
            />
            <Tooltip content={<ComparisonTooltip />} />
            <Bar
              dataKey="current"
              name={config.current_label}
              fill={CHART_COLORS.current}
              radius={[4, 4, 0, 0]}
              animationDuration={800}
            />
            <Bar
              dataKey="previous"
              name={config.previous_label}
              fill={CHART_COLORS.previous}
              radius={[4, 4, 0, 0]}
              animationDuration={800}
              animationBegin={200}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Delta summary cards */}
      <div className="mt-4 pt-4 border-t border-border-subtle grid grid-cols-2 md:grid-cols-4 gap-3">
        {data.map((item, idx) => {
          const isPositive = item.delta > 0;
          const format = METRIC_FORMATS[item.metric] || "number";
          return (
            <motion.div
              key={item.metric}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 + idx * 0.1 }}
              className={cn(
                "p-2 rounded-lg text-center",
                isPositive ? "bg-accent-emerald/10" : item.delta < 0 ? "bg-accent-neon-red/10" : "bg-surface-secondary"
              )}
            >
              <p className="text-text-muted text-xs mb-1">{item.name}</p>
              <p className={cn(
                "text-sm font-bold",
                isPositive ? "text-accent-emerald" : item.delta < 0 ? "text-accent-neon-red" : "text-text-primary"
              )}>
                {isPositive ? "+" : ""}{item.deltaPct.toFixed(1)}%
              </p>
              <p className="text-text-subtle text-xs mt-0.5">
                {format === "currency" ? formatCurrency(Math.abs(item.delta)) : formatNumber(Math.abs(item.delta))}
              </p>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
