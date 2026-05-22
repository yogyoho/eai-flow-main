"use client";

import { AlertCircle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import React from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ConnectionStatus } from "../types";
import { CONNECTION_STATUS_LABELS } from "../types";

const STATUS_CONFIG: Record<
  ConnectionStatus,
  {
    variant: "default" | "destructive" | "secondary" | "outline";
    className: string;
    icon: React.ReactNode;
  }
> = {
  connected: {
    variant: "outline",
    className: "border-success/30 text-success bg-success/10",
    icon: <CheckCircle2 className="h-3 w-3" />,
  },
  error: {
    variant: "destructive",
    className: "border-destructive/30 text-destructive bg-destructive/10",
    icon: <AlertCircle className="h-3 w-3" />,
  },
  disconnected: {
    variant: "secondary",
    className: "border-border text-muted-foreground bg-muted",
    icon: <XCircle className="h-3 w-3" />,
  },
  testing: {
    variant: "outline",
    className: "border-primary/30 text-primary bg-primary/10",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
  },
};

export function ConnectionStatusBadge({
  status,
}: {
  status: ConnectionStatus;
}) {
  const config = STATUS_CONFIG[status];

  return (
    <Badge variant={config.variant} className={cn(config.className, "gap-1")}>
      {config.icon}
      {CONNECTION_STATUS_LABELS[status]}
    </Badge>
  );
}
