"use client";

import { Wifi, WifiOff, Loader2, AlertCircle, CheckCircle } from "lucide-react";
import { ConnectionStatus as Status } from "@/hooks/useAgentChat";

interface ConnectionStatusProps {
  status: Status;
  className?: string;
}

const statusConfig: Record<Status, {
  icon: React.ReactNode;
  label: string;
  color: string;
  bgColor: string;
}> = {
  idle: {
    icon: <CheckCircle className="w-3 h-3" />,
    label: "Conectado",
    color: "text-green-400",
    bgColor: "bg-green-400/10",
  },
  connecting: {
    icon: <Loader2 className="w-3 h-3 animate-spin" />,
    label: "Conectando...",
    color: "text-yellow-400",
    bgColor: "bg-yellow-400/10",
  },
  streaming: {
    icon: <Wifi className="w-3 h-3 animate-pulse" />,
    label: "Recibiendo datos",
    color: "text-blue-400",
    bgColor: "bg-blue-400/10",
  },
  error: {
    icon: <AlertCircle className="w-3 h-3" />,
    label: "Error de conexion",
    color: "text-red-400",
    bgColor: "bg-red-400/10",
  },
  disconnected: {
    icon: <WifiOff className="w-3 h-3" />,
    label: "Desconectado",
    color: "text-gray-400",
    bgColor: "bg-gray-400/10",
  },
};

export function ConnectionStatusIndicator({ status, className = "" }: ConnectionStatusProps) {
  const config = statusConfig[status];

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${config.color} ${config.bgColor} ${className}`}
    >
      {config.icon}
      <span>{config.label}</span>
    </div>
  );
}

// Minimal dot indicator for compact spaces
export function ConnectionDot({ status }: { status: Status }) {
  const colors: Record<Status, string> = {
    idle: "bg-green-400",
    connecting: "bg-yellow-400 animate-pulse",
    streaming: "bg-blue-400 animate-pulse",
    error: "bg-red-400",
    disconnected: "bg-gray-400",
  };

  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${colors[status]}`}
      title={statusConfig[status].label}
    />
  );
}
