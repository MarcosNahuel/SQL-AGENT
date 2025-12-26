"use client";

import { motion } from "framer-motion";
import { cn, formatValue, resolveRef } from "@/lib/utils";
import { KpiCardConfig, DataPayload } from "@/lib/types";
import { TrendingUp, TrendingDown, DollarSign, ShoppingCart, Package, Users, Activity } from "lucide-react";

interface KpiCardProps {
  config: KpiCardConfig;
  payload?: DataPayload;
  index?: number;
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  sales: DollarSign,
  orders: ShoppingCart,
  products: Package,
  users: Users,
  activity: Activity,
};

export function KpiCard({ config, payload, index = 0 }: KpiCardProps) {
  const value = resolveRef(config.value_ref, payload as Record<string, unknown>);
  const deltaValue = config.delta_ref
    ? resolveRef(config.delta_ref, payload as Record<string, unknown>)
    : undefined;

  const formattedValue = formatValue(value, config.format || "number");

  const Icon = config.icon ? iconMap[config.icon] : DollarSign;
  const isPositive = deltaValue !== undefined && deltaValue > 0;
  const isNegative = deltaValue !== undefined && deltaValue < 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.3,
        delay: index * 0.05,
        ease: [0.25, 0.46, 0.45, 0.94]
      }}
      whileHover={{
        y: -2,
        transition: { duration: 0.15 }
      }}
      className={cn(
        "kpi-card border-glow p-3 relative overflow-hidden group",
        "cursor-default select-none"
      )}
    >
      {/* Subtle gradient overlay on hover */}
      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none">
        <div className={cn(
          "absolute inset-0",
          isPositive && "bg-gradient-to-br from-accent-emerald/5 to-transparent",
          isNegative && "bg-gradient-to-br from-accent-neon-red/5 to-transparent",
          !isPositive && !isNegative && "bg-gradient-to-br from-accent-blue/5 to-transparent"
        )} />
      </div>

      <div className="flex items-center justify-between relative z-10 gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-xs text-text-muted font-medium mb-0.5 truncate">
            {config.label}
          </p>

          <motion.p
            className="text-lg font-bold text-text-primary tracking-tight"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: index * 0.05 + 0.1, duration: 0.2 }}
          >
            {formattedValue}
          </motion.p>

          {deltaValue !== undefined && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: index * 0.05 + 0.15, duration: 0.2 }}
              className={cn(
                "flex items-center gap-1 mt-1 text-xs font-medium",
                isPositive && "text-accent-emerald",
                isNegative && "text-accent-neon-red",
                !isPositive && !isNegative && "text-text-muted"
              )}
            >
              {isPositive ? (
                <TrendingUp className="w-3 h-3" />
              ) : isNegative ? (
                <TrendingDown className="w-3 h-3" />
              ) : null}
              <span>{formatValue(Math.abs(deltaValue), "percent")}</span>
            </motion.div>
          )}
        </div>

        {/* Icon with glow effect */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: index * 0.05 + 0.1, duration: 0.2 }}
          className={cn(
            "p-2 rounded-lg relative flex-shrink-0",
            "bg-accent-blue/10 group-hover:bg-accent-blue/15 transition-colors duration-300"
          )}
        >
          <Icon className="w-4 h-4 text-accent-blue" />
        </motion.div>
      </div>

      {/* Bottom accent line */}
      <motion.div
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ delay: index * 0.1 + 0.4, duration: 0.5 }}
        className={cn(
          "absolute bottom-0 left-0 right-0 h-0.5 origin-left",
          isPositive && "bg-gradient-to-r from-accent-emerald/50 to-transparent",
          isNegative && "bg-gradient-to-r from-accent-neon-red/50 to-transparent",
          !isPositive && !isNegative && "bg-gradient-to-r from-accent-blue/30 to-transparent"
        )}
      />
    </motion.div>
  );
}
