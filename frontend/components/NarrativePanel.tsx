"use client";

import { NarrativeConfig } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Lightbulb, AlertCircle, Sparkles, FileText, Brain, Zap } from "lucide-react";

interface NarrativePanelProps {
  narratives: NarrativeConfig[];
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  headline: Zap,
  insight: Lightbulb,
  callout: AlertCircle,
  summary: Brain,
};

const styleMap: Record<string, { container: string; text: string }> = {
  headline: {
    container: "bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/20 rounded-xl px-4 py-3",
    text: "text-lg font-bold text-white",
  },
  summary: {
    container: "bg-gray-800/30 rounded-lg px-4 py-3",
    text: "text-gray-300 leading-relaxed",
  },
  insight: {
    container: "flex items-start gap-3 py-2",
    text: "text-gray-300",
  },
  callout: {
    container: "bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3 mt-2",
    text: "text-amber-300",
  },
};

export function NarrativePanel({ narratives }: NarrativePanelProps) {
  if (!narratives || narratives.length === 0) {
    return null;
  }

  // Separate by type for better organization
  const headline = narratives.find(n => n.type === "headline");
  const summary = narratives.find(n => n.type === "summary");
  const insights = narratives.filter(n => n.type === "insight");
  const callouts = narratives.filter(n => n.type === "callout");

  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
          <Sparkles className="w-4 h-4 text-white" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">Analisis AI</h3>
          <p className="text-xs text-gray-500">Razonamiento profundo (UltraThink)</p>
        </div>
      </div>

      {/* Headline - Main conclusion */}
      {headline && (
        <div className={styleMap.headline.container}>
          <div className="flex items-center gap-2 mb-1">
            <Zap className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-blue-400 uppercase tracking-wider font-medium">Conclusion</span>
          </div>
          <p className={styleMap.headline.text}>{headline.text}</p>
        </div>
      )}

      {/* Summary */}
      {summary && (
        <div className={styleMap.summary.container}>
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-4 h-4 text-gray-400" />
            <span className="text-xs text-gray-400 uppercase tracking-wider">Resumen Ejecutivo</span>
          </div>
          <p className={styleMap.summary.text}>{summary.text}</p>
        </div>
      )}

      {/* Insights */}
      {insights.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 mb-2">
            <Lightbulb className="w-4 h-4 text-yellow-400" />
            <span className="text-xs text-gray-400 uppercase tracking-wider">Insights Detallados</span>
          </div>
          <div className="space-y-2 pl-1">
            {insights.map((insight, idx) => (
              <div key={idx} className="flex items-start gap-3">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-2 flex-shrink-0" />
                <p className="text-gray-300 leading-relaxed">{insight.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Callouts / Recommendations */}
      {callouts.length > 0 && (
        <div className="space-y-2">
          {callouts.map((callout, idx) => (
            <div key={idx} className={styleMap.callout.container}>
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" />
                <p className={styleMap.callout.text}>{callout.text}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
