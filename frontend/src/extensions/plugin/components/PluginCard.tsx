"use client";

import { Download, Settings } from "lucide-react";
import React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { Plugin } from "@/extensions/plugin/types";
import { PLUGIN_TYPE_LABELS } from "@/extensions/plugin/types";
import { cn } from "@/lib/utils";

interface PluginCardProps {
  plugin: Plugin;
  onInstall?: () => void;
  onConfigure?: () => void;
  installed?: boolean;
}

const TYPE_COLORS: Record<string, string> = {
  data_connector: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  tool: "bg-purple-500/10 text-purple-600 border-purple-500/20",
  output: "bg-green-500/10 text-green-600 border-green-500/20",
  custom: "bg-orange-500/10 text-orange-600 border-orange-500/20",
};

const ICON_BG_COLORS: Record<string, string> = {
  data_connector: "bg-blue-500/10 text-blue-600",
  tool: "bg-purple-500/10 text-purple-600",
  output: "bg-green-500/10 text-green-600",
  custom: "bg-orange-500/10 text-orange-600",
};

export function PluginCard({
  plugin,
  onInstall,
  onConfigure,
  installed = false,
}: PluginCardProps) {
  const typeColor = TYPE_COLORS[plugin.type] ?? TYPE_COLORS.custom;
  const iconBg = ICON_BG_COLORS[plugin.type] ?? ICON_BG_COLORS.custom;
  const firstLetter = plugin.name.charAt(0).toUpperCase();

  return (
    <Card
      className={cn(
        "relative flex flex-col overflow-hidden transition-all hover:border-primary/30 hover:shadow-md",
        installed && "border-primary/20",
      )}
    >
      <div className="flex-1 p-5">
        {/* Header: Icon + Name + Type */}
        <div className="mb-3 flex items-start gap-3">
          <div
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-lg font-bold",
              iconBg,
            )}
          >
            {plugin.icon ? (
              <span className="text-xl">{plugin.icon}</span>
            ) : (
              firstLetter
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-foreground line-clamp-1">
                {plugin.name}
              </h3>
              <Badge variant="outline" className={cn("text-xs font-medium", typeColor)}>
                {PLUGIN_TYPE_LABELS[plugin.type]}
              </Badge>
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {plugin.author} &middot; v{plugin.version}
            </div>
          </div>
        </div>

        {/* Description */}
        {plugin.description && (
          <p className="mb-4 text-sm text-muted-foreground line-clamp-2">
            {plugin.description}
          </p>
        )}

        {/* Permissions */}
        {plugin.permissions.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {plugin.permissions.slice(0, 3).map((perm) => (
              <span
                key={perm}
                className="inline-block rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
              >
                {perm}
              </span>
            ))}
            {plugin.permissions.length > 3 && (
              <span className="text-xs text-muted-foreground">
                +{plugin.permissions.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Bottom Action */}
      <div className="flex items-center justify-end border-t border-border bg-muted/50 px-5 py-3">
        {installed ? (
          <Button
            variant="outline"
            size="sm"
            onClick={onConfigure}
            className="h-8 text-xs"
          >
            <Settings className="mr-1.5 h-3.5 w-3.5" />
            配置
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={onInstall}
            className="h-8 text-xs"
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            安装
          </Button>
        )}
      </div>
    </Card>
  );
}
