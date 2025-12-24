"use client";

import { cn, formatValue, resolveRef } from "@/lib/utils";
import { KpiCardConfig, DataPayload } from "@/lib/types";
import { TrendingUp, TrendingDown, DollarSign, ShoppingCart, Package, Users } from "lucide-react";

interface KpiCardProps {
  config: KpiCardConfig;
  payload?: DataPayload;
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  sales: DollarSign,
  orders: ShoppingCart,
  products: Package,
  users: Users,
};

export function KpiCard({ config, payload }: KpiCardProps) {
  const value = resolveRef(config.value_ref, payload as Record<string, unknown>);
  const deltaValue = config.delta_ref
    ? resolveRef(config.delta_ref, payload as Record<string, unknown>)
    : undefined;

  const formattedValue = formatValue(value, config.format);

  const Icon = config.icon ? iconMap[config.icon] : DollarSign;
  const isPositive = deltaValue !== undefined && deltaValue > 0;

  return (
    <div className="bg-gray-800/50 backdrop-blur border border-gray-700/50 rounded-xl p-5 hover:bg-gray-800/70 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-gray-400 font-medium mb-1">{config.label}</p>
          <p className="text-2xl font-bold text-white">{formattedValue}</p>

          {deltaValue !== undefined && (
            <div className={cn(
              "flex items-center gap-1 mt-2 text-sm font-medium",
              isPositive ? "text-green-400" : "text-red-400"
            )}>
              {isPositive ? (
                <TrendingUp className="w-4 h-4" />
              ) : (
                <TrendingDown className="w-4 h-4" />
              )}
              <span>{formatValue(Math.abs(deltaValue), "percent")}</span>
            </div>
          )}
        </div>

        <div className="p-2 bg-blue-500/10 rounded-lg">
          <Icon className="w-5 h-5 text-blue-400" />
        </div>
      </div>
    </div>
  );
}
