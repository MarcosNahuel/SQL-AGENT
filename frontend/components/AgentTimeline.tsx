"use client";

import { cn } from "@/lib/utils";
import {
  Search,
  Brain,
  Database,
  BarChart3,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";

export interface AgentStep {
  step: string;
  status: "start" | "progress" | "done" | "error";
  ts: string;
  message?: string;
  detail?: Record<string, unknown>;
}

interface AgentTimelineProps {
  steps: AgentStep[];
  className?: string;
}

const STEP_ICONS: Record<string, React.ElementType> = {
  init: Search,
  router: Brain,
  router_complete: Brain,
  data_agent: Database,
  sql_execution: Database,
  presentation_agent: BarChart3,
  complete: CheckCircle2,
  error: AlertCircle,
  default: Loader2,
};

const STEP_LABELS: Record<string, string> = {
  init: "Analizando pregunta",
  router: "Clasificando consulta",
  router_complete: "Tipo detectado",
  data_agent: "Preparando datos",
  sql_execution: "Ejecutando SQL",
  presentation_agent: "Generando dashboard",
  direct_response: "Generando respuesta",
  complete: "Completado",
  error: "Error",
};

export function AgentTimeline({ steps, className }: AgentTimelineProps) {
  if (!steps.length) return null;

  return (
    <div className={cn("space-y-2", className)}>
      <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
        Timeline del Agente
      </h4>
      <div className="space-y-1">
        {steps.map((step, idx) => {
          const Icon = STEP_ICONS[step.step] || STEP_ICONS.default;
          const label = step.message || STEP_LABELS[step.step] || step.step;
          const isLast = idx === steps.length - 1;
          const isDone = step.status === "done" || step.status === "progress";
          const isError = step.status === "error";

          return (
            <div
              key={`${step.step}-${idx}`}
              className={cn(
                "flex items-start gap-3 py-2 px-3 rounded-lg transition-all",
                isLast && !isDone && "bg-blue-500/10 border border-blue-500/20",
                isDone && "opacity-70",
                isError && "bg-red-500/10 border border-red-500/20"
              )}
            >
              <div
                className={cn(
                  "w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0",
                  isError
                    ? "bg-red-500/20 text-red-400"
                    : isDone
                    ? "bg-green-500/20 text-green-400"
                    : "bg-blue-500/20 text-blue-400"
                )}
              >
                {isLast && !isDone && !isError ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Icon className="w-3.5 h-3.5" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p
                  className={cn(
                    "text-sm",
                    isError ? "text-red-300" : "text-gray-300"
                  )}
                >
                  {label}
                </p>
                {step.detail && (
                  <p className="text-xs text-gray-500 mt-0.5 truncate">
                    {JSON.stringify(step.detail).slice(0, 50)}...
                  </p>
                )}
              </div>
              {isDone && (
                <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default AgentTimeline;
