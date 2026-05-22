"use client";

import { motion } from "framer-motion";
import { Code, Database, Edit, Globe, Loader2, RefreshCw, Trash2, Upload } from "lucide-react";
import React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DataSource, DataSourceType } from "../types";
import { AUTH_TYPE_LABELS, DATA_SOURCE_TYPE_LABELS, SYNC_MODE_LABELS } from "../types";

import { ConnectionStatusBadge } from "./ConnectionStatusBadge";

const TYPE_ICON_MAP: Record<DataSourceType, React.ReactNode> = {
  database: <Database className="h-5 w-5" />,
  api: <Code className="h-5 w-5" />,
  file: <Upload className="h-5 w-5" />,
  gis: <Globe className="h-5 w-5" />,
};

const TYPE_COLOR_MAP: Record<DataSourceType, string> = {
  database: "border-primary/20 bg-primary/10 text-primary",
  api: "border-amber-500/20 bg-amber-500/10 text-amber-600",
  file: "border-green-500/20 bg-green-500/10 text-green-600",
  gis: "border-purple-500/20 bg-purple-500/10 text-purple-600",
};

function formatDate(dateString: string | null): string {
  if (!dateString) return "从未同步";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateString));
}

interface DataSourceCardProps {
  source: DataSource;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
  onSync: () => void;
  testing?: boolean;
  syncing?: boolean;
}

export function DataSourceCard({
  source,
  onEdit,
  onDelete,
  onTest,
  onSync,
  testing = false,
  syncing = false,
}: DataSourceCardProps) {
  const typeColor = TYPE_COLOR_MAP[source.type];
  const typeIcon = TYPE_ICON_MAP[source.type];
  const typeLabel = DATA_SOURCE_TYPE_LABELS[source.type];
  const authLabel = AUTH_TYPE_LABELS[source.authType] ?? source.authType;
  const syncLabel = SYNC_MODE_LABELS[source.syncMode] ?? source.syncMode;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="group flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md"
    >
      {/* Top section */}
      <div className="flex-1 p-5">
        <div className="mb-4 flex items-start gap-3">
          <div
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border",
              typeColor,
            )}
          >
            {typeIcon}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="line-clamp-1 font-semibold text-foreground">
              {source.name}
            </h3>
            <div className="mt-1 flex items-center gap-2">
              <span
                className={cn(
                  "inline-block rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                  typeColor,
                )}
              >
                {typeLabel}
              </span>
              <ConnectionStatusBadge status={source.status} />
            </div>
          </div>
        </div>

        {/* Middle: 3-column grid */}
        <div className="grid grid-cols-3 gap-3 border-t border-border py-3">
          <div>
            <div className="mb-1 text-xs text-muted-foreground">认证方式</div>
            <div className="truncate text-sm font-medium text-foreground">
              {authLabel}
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs text-muted-foreground">同步模式</div>
            <div className="truncate text-sm font-medium text-foreground">
              {syncLabel}
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs text-muted-foreground">最近同步</div>
            <div className="text-sm font-medium text-foreground">
              {formatDate(source.lastSyncAt)}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <div className="flex items-center justify-between border-t border-border bg-muted/50 px-5 py-3">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={onTest}
            disabled={testing}
            className="h-7 w-7 text-muted-foreground hover:bg-primary/10 hover:text-primary"
            title="测试连接"
          >
            {testing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Database className="h-3.5 w-3.5" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onSync}
            disabled={syncing}
            className="h-7 w-7 text-muted-foreground hover:bg-primary/10 hover:text-primary"
            title="同步数据"
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", syncing && "animate-spin")}
            />
          </Button>
        </div>
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <Button
            variant="ghost"
            size="icon"
            onClick={onEdit}
            className="h-7 w-7 text-muted-foreground hover:bg-muted hover:text-foreground"
            title="编辑"
          >
            <Edit className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onDelete}
            className="h-7 w-7 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            title="删除"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
