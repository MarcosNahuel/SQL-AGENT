/**
 * Zod validators for AI SDK v5 custom data parts
 * These validate the custom data streamed from the backend
 */
import { z } from 'zod';

// ============ Trace Part ============
export const TracePartSchema = z.object({
  trace_id: z.string(),
  request_id: z.string().optional(),
});
export type TracePart = z.infer<typeof TracePartSchema>;

// ============ Agent Step Part ============
export const AgentStepPartSchema = z.object({
  step: z.string(),
  status: z.enum(['start', 'progress', 'done', 'error']),
  ts: z.string(),
  detail: z.record(z.string(), z.unknown()).optional(),
  message: z.string().optional(),
}).catchall(z.unknown());
export type AgentStepPart = z.infer<typeof AgentStepPartSchema>;

// ============ SQL Meta Part ============
export const SqlMetaPartSchema = z.object({
  query_id: z.string(),
  row_count: z.number(),
  duration_ms: z.number(),
  safe: z.boolean(),
  view_or_template: z.string().optional(),
});
export type SqlMetaPart = z.infer<typeof SqlMetaPartSchema>;

// ============ KPI Card Config ============
export const KpiCardConfigSchema = z.object({
  type: z.literal('kpi_card').optional(),
  label: z.string(),
  value_ref: z.string(),
  format: z.enum(['currency', 'number', 'percent']).optional(),
  delta_ref: z.string().nullable().optional(),
  icon: z.string().nullable().optional(),
});
export type KpiCardConfig = z.infer<typeof KpiCardConfigSchema>;

// ============ Chart Config ============
export const ChartConfigSchema = z.object({
  type: z.enum(['line_chart', 'bar_chart', 'area_chart', 'table']),
  title: z.string(),
  dataset_ref: z.string(),
  x_axis: z.string().optional(),
  y_axis: z.string().optional(),
  columns: z.array(z.string()).optional(),
  max_rows: z.number().optional(),
  color: z.string().nullable().optional(),
});
export type ChartConfig = z.infer<typeof ChartConfigSchema>;

// ============ Table Config ============
export const TableConfigSchema = z.object({
  ref: z.string().optional(),
  title: z.string(),
  columns: z.array(z.object({
    key: z.string(),
    label: z.string(),
    format: z.string().optional(),
  })).optional(),
  data: z.array(z.record(z.string(), z.unknown())).optional(),
});
export type TableConfig = z.infer<typeof TableConfigSchema>;

// ============ Narrative Config ============
export const NarrativeConfigSchema = z.object({
  type: z.enum(['headline', 'insight', 'callout', 'summary']),
  text: z.string(),
  icon: z.string().nullable().optional(),
});
export type NarrativeConfig = z.infer<typeof NarrativeConfigSchema>;

// ============ Filter Config ============
export const FilterConfigSchema = z.object({
  date_from: z.string().optional(),
  date_to: z.string().optional(),
  applied_filters: z.record(z.string(), z.unknown()).optional(),
});
export type FilterConfig = z.infer<typeof FilterConfigSchema>;

// ============ Slot Config ============
export const SlotConfigSchema = z.object({
  // Accept both object format and empty array from backend
  filters: z.union([FilterConfigSchema, z.array(z.unknown())]).optional(),
  series: z.array(KpiCardConfigSchema).optional(),
  charts: z.array(ChartConfigSchema).optional(),
  tables: z.array(TableConfigSchema).optional(),
  narrative: z.array(NarrativeConfigSchema).optional(),
});
export type SlotConfig = z.infer<typeof SlotConfigSchema>;

// ============ Dashboard Spec ============
export const DashboardSpecSchema = z.object({
  title: z.string(),
  subtitle: z.string().nullable().optional(),
  conclusion: z.string().nullable().optional(),
  slots: SlotConfigSchema,
  generated_at: z.string().nullable().optional(),
});
export type DashboardSpec = z.infer<typeof DashboardSpecSchema>;

// ============ Dashboard Data Part ============
export const DashboardPartSchema = DashboardSpecSchema;
export type DashboardPart = z.infer<typeof DashboardPartSchema>;

// ============ Data Payload Schema ============
// Minimal validation for Zod v4 compatibility - trust backend data
export const DataPayloadSchema = z.object({
  kpis: z.unknown().nullable().optional(),
  time_series: z.unknown().nullable().optional(),
  top_items: z.unknown().nullable().optional(),
  tables: z.unknown().nullable().optional(),
}).passthrough();

// Type definition for runtime use (not strictly validated)
export interface DataPayload {
  kpis?: Record<string, unknown> | null;
  time_series?: Array<{
    series_name: string;
    points: Array<{
      date: string;
      value: number;
      label?: string | null;
    }>;
  }> | null;
  top_items?: Array<{
    ranking_name: string;
    items: Array<{
      title: string;
      value: number;
      rank?: number;
      id?: string;
      extra?: Record<string, unknown>;
    }>;
    metric?: string;
  }> | null;
  tables?: Array<{
    name: string;
    rows: Array<Record<string, unknown>>;
  }> | null;
}

// ============ Image Part ============
export const ImagePartSchema = z.object({
  image_url: z.string().optional(),
  alt: z.string().optional(),
});
export type ImagePart = z.infer<typeof ImagePartSchema>;

// ============ Validators ============
export function validateTracePart(data: unknown): TracePart | null {
  const result = TracePartSchema.safeParse(data);
  return result.success ? result.data : null;
}

export function validateAgentStepPart(data: unknown): AgentStepPart | null {
  const result = AgentStepPartSchema.safeParse(data);
  return result.success ? result.data : null;
}

export function validateSqlMetaPart(data: unknown): SqlMetaPart | null {
  const result = SqlMetaPartSchema.safeParse(data);
  return result.success ? result.data : null;
}

export function validateDashboardPart(data: unknown): DashboardPart | null {
  const result = DashboardPartSchema.safeParse(data);
  return result.success ? result.data : null;
}

export function validateDataPayload(data: unknown): DataPayload | null {
  // Minimal validation - just check it's an object with expected structure
  if (!data || typeof data !== 'object') return null;
  const payload = data as DataPayload;
  // Basic sanity check - at least one expected field should exist
  if ('kpis' in payload || 'time_series' in payload || 'top_items' in payload || 'tables' in payload) {
    return payload;
  }
  return null;
}

export function validateImagePart(data: unknown): ImagePart | null {
  const result = ImagePartSchema.safeParse(data);
  return result.success ? result.data : null;
}
