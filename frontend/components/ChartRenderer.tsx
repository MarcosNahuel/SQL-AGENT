"use client";

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
import { formatCurrency, formatNumber } from "@/lib/utils";

interface ChartRendererProps {
  config: ChartConfig;
  payload?: DataPayload;
}

// Paleta de colores moderna
const CHART_COLORS = {
  primary: "#3b82f6",
  secondary: "#8b5cf6",
  success: "#10b981",
  warning: "#f59e0b",
  danger: "#ef4444",
  info: "#06b6d4",
  gradient: {
    start: "#3b82f6",
    end: "#8b5cf6"
  }
};

const PIE_COLORS = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#06b6d4", "#ec4899", "#84cc16"];

function CustomTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || !payload.length) return null;

  const data = payload[0].payload;

  return (
    <div className="bg-gray-900/95 backdrop-blur-sm border border-gray-700 rounded-xl px-4 py-3 shadow-2xl">
      <p className="text-gray-400 text-xs font-medium mb-2 uppercase tracking-wide">{label}</p>
      {payload.map((entry, index) => (
        <div key={index} className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: entry.color || CHART_COLORS.primary }}
          />
          <p className="text-white font-semibold text-lg">
            {formatCurrency(entry.value as number)}
          </p>
        </div>
      ))}
      {data?.order_count && (
        <p className="text-gray-500 text-xs mt-1">
          {data.order_count} ordenes
        </p>
      )}
      {data?.units_sold && (
        <p className="text-gray-500 text-xs mt-1">
          {data.units_sold} unidades vendidas
        </p>
      )}
    </div>
  );
}

function BarTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload || !payload.length) return null;

  const data = payload[0].payload;

  return (
    <div className="bg-gray-900/95 backdrop-blur-sm border border-gray-700 rounded-xl px-4 py-3 shadow-2xl max-w-sm">
      {data?.rank && (
        <div className="flex items-center gap-2 mb-2">
          <span className="bg-blue-500 text-white text-xs font-bold px-2 py-0.5 rounded">
            #{data.rank}
          </span>
          <span className="text-gray-400 text-xs">Top Producto</span>
        </div>
      )}
      <p className="text-white font-medium text-sm mb-2 leading-tight">
        {data?.fullName || data?.name}
      </p>
      <div className="flex items-baseline gap-1">
        <p className="text-emerald-400 font-bold text-xl">
          {formatCurrency(payload[0].value as number)}
        </p>
        <span className="text-gray-500 text-xs">revenue</span>
      </div>
      {(data?.units_sold || data?.extra?.units_sold) && (
        <p className="text-gray-400 text-sm mt-1">
          <span className="text-white font-medium">
            {formatNumber(data.units_sold || data.extra.units_sold)}
          </span> unidades vendidas
        </p>
      )}
    </div>
  );
}

export function ChartRenderer({ config, payload }: ChartRendererProps) {
  // Extract data based on dataset_ref
  const refParts = config.dataset_ref.split(".");
  const [prefix, name] = refParts;

  let data: Array<Record<string, unknown>> = [];

  if (prefix === "ts" && payload?.time_series) {
    const series = payload.time_series.find(
      (ts: TimeSeriesData) => ts.series_name === name || config.dataset_ref === `ts.${ts.series_name}`
    );
    if (series) {
      data = series.points.map((p) => ({
        date: p.date.slice(5), // MM-DD format
        fullDate: p.date,
        value: p.value,
        order_count: (p as Record<string, unknown>).order_count
      }));
    }
  } else if (prefix === "top" && payload?.top_items) {
    const ranking = payload.top_items.find(
      (ti: TopItemsData) => ti.ranking_name === name || config.dataset_ref === `top.${ti.ranking_name}`
    );
    if (ranking) {
      // Ordenar explícitamente por valor descendente y tomar top 10
      const sortedItems = [...ranking.items]
        .sort((a, b) => b.value - a.value)
        .slice(0, 10);

      data = sortedItems.map((item, idx) => ({
        name: `#${idx + 1} ${item.title.slice(0, 20)}${item.title.length > 20 ? "..." : ""}`,
        shortName: item.title.slice(0, 18) + (item.title.length > 18 ? "..." : ""),
        fullName: item.title,
        value: item.value,
        rank: idx + 1,
        units_sold: item.extra?.units_sold,
        extra: item.extra
      }));
    }
  }

  if (data.length === 0) {
    return (
      <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-white mb-4">{config.title}</h3>
        <div className="h-48 flex items-center justify-center text-gray-500">
          <div className="text-center">
            <svg className="w-12 h-12 mx-auto mb-2 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p>No hay datos disponibles</p>
          </div>
        </div>
      </div>
    );
  }

  const chartColor = config.color || CHART_COLORS.primary;
  // Altura dinámica: 50px por item para bar charts (mínimo 320)
  const chartHeight = config.type === "bar_chart" ? Math.max(380, data.length * 50) : 320;

  // Calculate average for reference line
  const avgValue = data.reduce((sum, d) => sum + (d.value as number), 0) / data.length;

  return (
    <div className="bg-gradient-to-br from-gray-800/80 to-gray-900/80 border border-gray-700/50 rounded-xl p-5 shadow-xl">
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-lg font-semibold text-white">{config.title}</h3>
        {config.type === "line_chart" && (
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <div className="w-8 h-0.5 bg-gray-500 opacity-50" style={{ borderStyle: 'dashed' }} />
            <span>Promedio: {formatCurrency(avgValue)}</span>
          </div>
        )}
      </div>

      <div style={{ height: chartHeight }}>
        <ResponsiveContainer width="100%" height="100%">
          {config.type === "line_chart" ? (
            <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="colorGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={chartColor} stopOpacity={0.3}/>
                  <stop offset="95%" stopColor={chartColor} stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#374151"
                vertical={false}
              />
              <XAxis
                dataKey="date"
                stroke="#6b7280"
                fontSize={11}
                tickLine={false}
                axisLine={{ stroke: '#374151' }}
                tick={{ fill: '#9ca3af' }}
              />
              <YAxis
                stroke="#6b7280"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${formatNumber(v / 1000000)}M`}
                tick={{ fill: '#9ca3af' }}
                width={65}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                y={avgValue}
                stroke="#6b7280"
                strokeDasharray="5 5"
                strokeOpacity={0.5}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={chartColor}
                strokeWidth={2.5}
                fill="url(#colorGradient)"
                animationDuration={1000}
                animationEasing="ease-out"
              />
            </AreaChart>
          ) : config.type === "area_chart" ? (
            <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={chartColor} stopOpacity={0.4}/>
                  <stop offset="95%" stopColor={chartColor} stopOpacity={0.05}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
              <XAxis
                dataKey="date"
                stroke="#6b7280"
                fontSize={11}
                tickLine={false}
                tick={{ fill: '#9ca3af' }}
              />
              <YAxis
                stroke="#6b7280"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${formatNumber(v / 1000)}k`}
                tick={{ fill: '#9ca3af' }}
                width={60}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="value"
                stroke={chartColor}
                fill="url(#areaGradient)"
                strokeWidth={2}
                animationDuration={800}
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
                animationDuration={800}
                animationEasing="ease-out"
              >
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={PIE_COLORS[index % PIE_COLORS.length]}
                    stroke="transparent"
                  />
                ))}
              </Pie>
              <Tooltip content={<BarTooltip />} />
              <Legend
                verticalAlign="bottom"
                height={36}
                formatter={(value) => <span className="text-gray-400 text-xs">{value}</span>}
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
                <linearGradient id="barGradient" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor={chartColor} stopOpacity={0.8}/>
                  <stop offset="100%" stopColor={CHART_COLORS.secondary} stopOpacity={0.9}/>
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#374151"
                horizontal={false}
              />
              <XAxis
                type="number"
                stroke="#6b7280"
                fontSize={10}
                tickLine={false}
                axisLine={{ stroke: '#374151' }}
                tickFormatter={(v) => `$${formatNumber(v / 1000000)}M`}
                tick={{ fill: '#9ca3af' }}
              />
              <YAxis
                type="category"
                dataKey="name"
                stroke="#6b7280"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                width={160}
                tick={{ fill: '#d1d5db' }}
              />
              <Tooltip content={<BarTooltip />} cursor={{ fill: 'rgba(59, 130, 246, 0.1)' }} />
              <Bar
                dataKey="value"
                fill="url(#barGradient)"
                radius={[0, 6, 6, 0]}
                animationDuration={800}
                animationEasing="ease-out"
              />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>

      {/* Summary stats */}
      {config.type !== "pie_chart" && data.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-700/50 flex items-center justify-between text-xs text-gray-500">
          <span>{data.length} {config.type === "bar_chart" ? "productos" : "dias"}</span>
          <span>
            Total: {formatCurrency(data.reduce((sum, d) => sum + (d.value as number), 0))}
          </span>
        </div>
      )}
    </div>
  );
}
