// API Types - matching backend Pydantic schemas

// SSE Streaming Event Types
export interface StreamEvent {
  event: "start" | "progress" | "complete" | "error";
  message: string;
  step?: string;
  detail?: string;
  trace_id?: string;
  timestamp?: string;
  result?: {
    success: boolean;
    dashboard_spec: DashboardSpec;
    data_payload: DataPayload;
    data_meta: DataMeta;
  };
}

export interface InsightRequest {
  question: string;
  date_from?: string;
  date_to?: string;
  filters?: Record<string, unknown>;
}

export interface InsightResponse {
  success: boolean;
  trace_id: string;
  dashboard_spec?: DashboardSpec;
  data_payload?: DataPayload;
  data_meta?: DataMeta;
  error?: string;
  execution_time_ms?: number;
}

export interface DashboardSpec {
  title: string;
  subtitle?: string | null;
  conclusion?: string | null;  // Conclusion corta para mostrar en el chat
  slots: SlotConfig;
  generated_at?: string | null;
}

export interface SlotConfig {
  filters?: FilterConfig[] | Record<string, unknown> | unknown[];
  series?: KpiCardConfig[];
  charts?: (ChartConfig | TableConfig | ComparisonChartConfig)[];
  narrative?: NarrativeConfig[];
}

export interface FilterConfig {
  type: string;
  from?: string;
  to?: string;
}

export interface KpiCardConfig {
  type?: "kpi_card";
  label: string;
  value_ref: string;
  format?: "currency" | "number" | "percent";
  delta_ref?: string | null;
  icon?: string | null;
}

export interface ChartConfig {
  type: "line_chart" | "bar_chart" | "area_chart" | "pie_chart" | "table";
  title: string;
  dataset_ref: string;
  x_axis?: string;
  y_axis?: string;
  columns?: string[];
  max_rows?: number;
  color?: string | null;
}

export interface ComparisonChartConfig {
  type: "comparison_bar" | "comparison_kpi";
  title: string;
  current_label: string;
  previous_label: string;
  metrics: string[];
  dataset_ref: string;
}

export interface TableConfig {
  type: "table";
  title: string;
  dataset_ref: string;
  columns: string[];
  max_rows: number;
}

export interface NarrativeConfig {
  type: "headline" | "insight" | "callout" | "summary";
  text: string;
  icon?: string | null;
}

export interface DataPayload {
  kpis?: KpiData;
  time_series?: TimeSeriesData[];
  top_items?: TopItemsData[];
  tables?: TableData[];
  comparison?: ComparisonData;
}

export interface ComparisonPeriod {
  label: string;
  date_from: string;
  date_to: string;
  kpis?: KpiData;
}

export interface ComparisonData {
  is_comparison: boolean;
  current_period: ComparisonPeriod;
  previous_period: ComparisonPeriod;
  delta_sales?: number;
  delta_sales_pct?: number;
  delta_orders?: number;
  delta_orders_pct?: number;
  delta_avg_order?: number;
  delta_avg_order_pct?: number;
  delta_units?: number;
  delta_units_pct?: number;
}

export interface KpiData {
  total_sales?: number;
  total_orders?: number;
  avg_order_value?: number;
  total_units?: number;
  total_interactions?: number;
  escalated_count?: number;
  escalation_rate?: number;
  auto_response_rate?: number;
  [key: string]: number | undefined;
}

export interface TimeSeriesData {
  series_name: string;
  points: TimeSeriesPoint[];
}

export interface TimeSeriesPoint {
  date: string;
  value: number;
  label?: string;
}

export interface TopItemsData {
  ranking_name: string;
  items: TopItem[];
  metric: string;
}

export interface TopItem {
  rank: number;
  id: string;
  title: string;
  value: number;
  extra?: Record<string, unknown>;
}

export interface TableData {
  name: string;
  rows: Record<string, unknown>[];
}

export interface DataMeta {
  available_refs: string[];
  datasets_count: number;
  has_kpis: boolean;
  has_time_series: boolean;
  has_top_items: boolean;
}
