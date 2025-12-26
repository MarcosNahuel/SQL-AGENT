"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  TooltipProps,
  Legend,
  ReferenceLine,
} from "recharts";
import { ChartConfig, DataPayload, TimeSeriesData, TopItemsData } from "@/lib/types";
import { formatCurrency, formatNumber, cn } from "@/lib/utils";

interface ChartRendererProps {
  config: ChartConfig;
  payload?: DataPayload;
  index?: number;
}

// OLED-optimized color palette
const CHART_COLORS = {
  emerald: "#10b981",
  emeraldGlow: "rgba(16, 185, 129, 0.4)",
  neonRed: "#ff3366",
  neonRedGlow: "rgba(255, 51, 102, 0.4)",
  blue: "#3b82f6",
  blueGlow: "rgba(59, 130, 246, 0.3)",
  purple: "#8b5cf6",
  cyan: "#06b6d4",
  amber: "#f59e0b",
};

const PIE_COLORS = [
  CHART_COLORS.blue,
  CHART_COLORS.purple,
  CHART_COLORS.emerald,
  CHART_COLORS.amber,
  CHART_COLORS.neonRed,
  CHART_COLORS.cyan,
  "#ec4899",
  "#84cc16",
];

// Glass-Hydration Tooltip with high refraction effect
function GlassTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || !payload.length) return null;

  const data = payload[0].payload;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 5 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      className="glass-tooltip px-4 py-3 shadow-2xl"
    >
      <p className="text-text-subtle text-xs font-medium mb-2 uppercase tracking-wide">
        {label}
      </p>
      {payload.map((entry, index) => (
        <div key={index} className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full shadow-lg"
            style={{
              backgroundColor: entry.color || CHART_COLORS.blue,
              boxShadow: `0 0 8px ${entry.color || CHART_COLORS.blueGlow}`,
            }}
          />
          <p className="text-text-primary font-semibold text-lg">
            {formatCurrency(entry.value as number)}
          </p>
        </div>
      ))}
      {data?.order_count && (
        <p className="text-text-muted text-xs mt-1.5">
          {data.order_count} ordenes
        </p>
      )}
      {data?.units_sold && (
        <p className="text-text-muted text-xs mt-1">
          {data.units_sold} unidades vendidas
        </p>
      )}
    </motion.div>
  );
}

function BarTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload || !payload.length) return null;

  const data = payload[0].payload;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-tooltip px-4 py-3 max-w-sm"
    >
      {data?.rank && (
        <div className="flex items-center gap-2 mb-2">
          <span
            className="text-xs font-bold px-2 py-0.5 rounded-md"
            style={{
              background: `linear-gradient(135deg, ${CHART_COLORS.blue}, ${CHART_COLORS.purple})`,
              color: "white",
            }}
          >
            #{data.rank}
          </span>
          <span className="text-text-subtle text-xs">Top Producto</span>
        </div>
      )}
      <p className="text-text-primary font-medium text-sm mb-2 leading-tight">
        {data?.fullName || data?.name}
      </p>
      <div className="flex items-baseline gap-1.5">
        <p className="text-accent-emerald font-bold text-xl">
          {formatCurrency(payload[0].value as number)}
        </p>
        <span className="text-text-subtle text-xs">revenue</span>
      </div>
      {(data?.units_sold || data?.extra?.units_sold) && (
        <p className="text-text-muted text-sm mt-1.5">
          <span className="text-text-primary font-medium">
            {formatNumber(data.units_sold || data.extra.units_sold)}
          </span>{" "}
          unidades vendidas
        </p>
      )}
    </motion.div>
  );
}

export function ChartRenderer({ config, payload, index = 0 }: ChartRendererProps) {
  // Extract data based on dataset_ref
  const refParts = config.dataset_ref.split(".");
  const [prefix, name] = refParts;

  const { data, trend } = useMemo(() => {
    let chartData: Array<Record<string, unknown>> = [];
    let trendDirection: "up" | "down" | "neutral" = "neutral";

    if (prefix === "ts" && payload?.time_series) {
      const series = payload.time_series.find(
        (ts: TimeSeriesData) =>
          ts.series_name === name || config.dataset_ref === `ts.${ts.series_name}`
      );
      if (series) {
        chartData = series.points.map((p) => ({
          date: p.date.slice(5), // MM-DD format
          fullDate: p.date,
          value: p.value,
          order_count: (p as unknown as Record<string, unknown>).order_count,
        }));

        // Calculate trend based on first vs last values
        if (chartData.length >= 2) {
          const firstValue = chartData[0].value as number;
          const lastValue = chartData[chartData.length - 1].value as number;
          trendDirection = lastValue > firstValue ? "up" : lastValue < firstValue ? "down" : "neutral";
        }
      }
    } else if (prefix === "top" && payload?.top_items) {
      const ranking = payload.top_items.find(
        (ti: TopItemsData) =>
          ti.ranking_name === name || config.dataset_ref === `top.${ti.ranking_name}`
      );
      if (ranking) {
        const sortedItems = [...ranking.items]
          .sort((a, b) => b.value - a.value)
          .slice(0, 10);

        chartData = sortedItems.map((item, idx) => ({
          name: `#${idx + 1} ${item.title.slice(0, 20)}${item.title.length > 20 ? "..." : ""}`,
          shortName: item.title.slice(0, 18) + (item.title.length > 18 ? "..." : ""),
          fullName: item.title,
          value: item.value,
          rank: idx + 1,
          units_sold: item.extra?.units_sold,
          extra: item.extra,
        }));
      }
    }

    return { data: chartData, trend: trendDirection };
  }, [config.dataset_ref, payload, prefix, name]);

  // Adaptive colors based on trend
  const chartColor = useMemo(() => {
    if (config.type === "line_chart" || config.type === "area_chart") {
      return trend === "up" ? CHART_COLORS.emerald : trend === "down" ? CHART_COLORS.neonRed : CHART_COLORS.blue;
    }
    return config.color || CHART_COLORS.blue;
  }, [config.type, config.color, trend]);

  const chartGlow = useMemo(() => {
    if (trend === "up") return CHART_COLORS.emeraldGlow;
    if (trend === "down") return CHART_COLORS.neonRedGlow;
    return CHART_COLORS.blueGlow;
  }, [trend]);

  if (data.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: index * 0.1 }}
        className="chart-container p-6"
      >
        <h3 className="text-lg font-semibold text-text-primary mb-4">{config.title}</h3>
        <div className="h-48 flex items-center justify-center text-text-muted">
          <div className="text-center">
            <svg
              className="w-12 h-12 mx-auto mb-2 text-text-subtle"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
            <p>No hay datos disponibles</p>
          </div>
        </div>
      </motion.div>
    );
  }

  const chartHeight = config.type === "bar_chart" ? Math.max(280, data.length * 32) : 220;
  const avgValue = data.reduce((sum, d) => sum + (d.value as number), 0) / data.length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.15 }}
      className="chart-container p-4 relative overflow-hidden group"
    >
      {/* Subtle glow effect based on trend */}
      <div
        className="absolute -top-20 -right-20 w-40 h-40 rounded-full opacity-20 blur-3xl pointer-events-none transition-opacity duration-500 group-hover:opacity-30"
        style={{ background: chartGlow }}
      />

      <div className="flex items-center justify-between mb-3 relative z-10">
        <h3 className="text-sm font-semibold text-text-primary">{config.title}</h3>
        {config.type === "line_chart" && (
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <div
              className="w-8 h-0.5 opacity-50"
              style={{ borderBottom: "2px dashed rgba(255,255,255,0.3)" }}
            />
            <span>Promedio: {formatCurrency(avgValue)}</span>
          </div>
        )}
        {/* Trend indicator */}
        {(config.type === "line_chart" || config.type === "area_chart") && trend !== "neutral" && (
          <div
            className={cn(
              "px-2 py-0.5 rounded-full text-xs font-medium",
              trend === "up" ? "bg-accent-emerald/20 text-accent-emerald" : "bg-accent-neon-red/20 text-accent-neon-red"
            )}
          >
            {trend === "up" ? "Subiendo" : "Bajando"}
          </div>
        )}
      </div>

      <div style={{ height: chartHeight }} className="relative z-10">
        <ResponsiveContainer width="100%" height="100%">
          {config.type === "line_chart" ? (
            <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`gradient-${index}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={chartColor} stopOpacity={0.5} />
                  <stop offset="95%" stopColor={chartColor} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.06)"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                stroke="rgba(255,255,255,0.3)"
                fontSize={11}
                tickLine={false}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                tick={{ fill: "rgba(255,255,255,0.5)" }}
              />
              <YAxis
                stroke="rgba(255,255,255,0.3)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${formatNumber(v / 1000000)}M`}
                tick={{ fill: "rgba(255,255,255,0.5)" }}
                width={65}
              />
              <Tooltip content={<GlassTooltip />} />
              <ReferenceLine
                y={avgValue}
                stroke="rgba(255,255,255,0.2)"
                strokeDasharray="5 5"
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={chartColor}
                strokeWidth={3}
                fill={`url(#gradient-${index})`}
                animationDuration={1200}
                animationEasing="ease-out"
                dot={false}
                activeDot={{
                  r: 8,
                  fill: chartColor,
                  stroke: "#000",
                  strokeWidth: 2,
                  style: { filter: `drop-shadow(0 0 12px ${chartGlow})` },
                }}
              />
            </AreaChart>
          ) : config.type === "area_chart" ? (
            <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`areaGradient-${index}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={chartColor} stopOpacity={0.4} />
                  <stop offset="95%" stopColor={chartColor} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.06)"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                stroke="rgba(255,255,255,0.3)"
                fontSize={11}
                tickLine={false}
                tick={{ fill: "rgba(255,255,255,0.5)" }}
              />
              <YAxis
                stroke="rgba(255,255,255,0.3)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${formatNumber(v / 1000)}k`}
                tick={{ fill: "rgba(255,255,255,0.5)" }}
                width={60}
              />
              <Tooltip content={<GlassTooltip />} />
              <Area
                type="monotone"
                dataKey="value"
                stroke={chartColor}
                fill={`url(#areaGradient-${index})`}
                strokeWidth={2}
                animationDuration={1000}
              />
            </AreaChart>
          ) : config.type === "pie_chart" ? (
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="value"
                animationDuration={1000}
                animationEasing="ease-out"
              >
                {data.map((_, idx) => (
                  <Cell
                    key={`cell-${idx}`}
                    fill={PIE_COLORS[idx % PIE_COLORS.length]}
                    stroke="transparent"
                    style={{
                      filter: `drop-shadow(0 0 4px ${PIE_COLORS[idx % PIE_COLORS.length]}40)`,
                    }}
                  />
                ))}
              </Pie>
              <Tooltip content={<BarTooltip />} />
              <Legend
                verticalAlign="bottom"
                height={36}
                formatter={(value) => (
                  <span className="text-text-muted text-xs">{value}</span>
                )}
              />
            </PieChart>
          ) : (
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: 10, right: 20, top: 5, bottom: 5 }}
              barCategoryGap="15%"
            >
              <defs>
                <linearGradient id={`barGradient-${index}`} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor={CHART_COLORS.blue} stopOpacity={1} />
                  <stop offset="100%" stopColor={CHART_COLORS.purple} stopOpacity={1} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.06)"
                horizontal={false}
              />
              <XAxis
                type="number"
                stroke="rgba(255,255,255,0.3)"
                fontSize={10}
                tickLine={false}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                tickFormatter={(v) => `$${formatNumber(v / 1000000)}M`}
                tick={{ fill: "rgba(255,255,255,0.5)" }}
              />
              <YAxis
                type="category"
                dataKey="name"
                stroke="rgba(255,255,255,0.3)"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                width={160}
                tick={{ fill: "rgba(255,255,255,0.7)" }}
              />
              <Tooltip
                content={<BarTooltip />}
                cursor={{ fill: "rgba(59, 130, 246, 0.08)" }}
              />
              <Bar
                dataKey="value"
                fill={`url(#barGradient-${index})`}
                radius={[0, 6, 6, 0]}
                animationDuration={1000}
                animationEasing="ease-out"
              />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>

      {/* Summary stats */}
      {config.type !== "pie_chart" && data.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="mt-4 pt-4 border-t border-border-subtle flex items-center justify-between text-xs text-text-muted"
        >
          <span>
            {data.length} {config.type === "bar_chart" ? "productos" : "dias"}
          </span>
          <span>Total: {formatCurrency(data.reduce((sum, d) => sum + (d.value as number), 0))}</span>
        </motion.div>
      )}
    </motion.div>
  );
}
