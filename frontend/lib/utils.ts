import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "ARS",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("es-AR").format(value);
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatValue(value: number | undefined, format: string): string {
  if (value === undefined || value === null) return "N/A";

  switch (format) {
    case "currency":
      return formatCurrency(value);
    case "percent":
      return formatPercent(value);
    case "number":
    default:
      return formatNumber(value);
  }
}

export function resolveRef(ref: string, payload: Record<string, unknown> | undefined): number | undefined {
  if (!payload || !ref) return undefined;

  const parts = ref.split(".");
  if (parts.length !== 2) return undefined;

  const [prefix, key] = parts;

  if (prefix === "kpi" && payload.kpis) {
    return (payload.kpis as Record<string, number>)[key];
  }

  return undefined;
}
