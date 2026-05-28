"use client";

import { Loader2 } from "lucide-react";
import * as React from "react";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export interface ChatModelChoice {
  name: string;
  display_name: string;
}

export interface ChatModelGroup {
  provider: string;
  models: ChatModelChoice[];
}

interface GroupedModelSelectProps {
  value: string;
  onChange: (value: string) => void;
  groups: ChatModelGroup[];
  placeholder?: string;
  disabled?: boolean;
  /** Per-model status: available / unavailable / error */
  modelStatuses?: Record<string, { status?: string; message?: string | null }>;
  validatingModels?: Set<string>;
  onValidate?: (modelName: string) => void;
}

function getStatusIcon(status?: string) {
  if (!status) return null;
  if (status === "available") return "✓";
  if (status === "unavailable") return "✗";
  if (status === "error") return "⚠";
  return null;
}

function getStatusColor(status?: string) {
  if (!status) return "text-muted-foreground";
  if (status === "available") return "text-green-500";
  if (status === "unavailable") return "text-red-500";
  if (status === "error") return "text-yellow-500";
  return "text-muted-foreground";
}

function getStatusBgColor(status?: string) {
  if (!status) return "";
  if (status === "available") return "bg-green-500/10";
  if (status === "unavailable") return "bg-red-500/10";
  if (status === "error") return "bg-yellow-500/10";
  return "";
}

export function GroupedModelSelect({
  value,
  onChange,
  groups,
  placeholder = "请选择模型",
  disabled = false,
  modelStatuses = {},
  validatingModels,
  onValidate,
}: GroupedModelSelectProps) {
  const currentModel = groups
    .flatMap((g) => g.models)
    .find((m) => m.name === value);

  const currentStatus = value ? modelStatuses[value] : undefined;
  const isValidating = value && validatingModels?.has(value);
  const statusIcon = getStatusIcon(currentStatus?.status);
  const statusColor = getStatusColor(currentStatus?.status);
  const statusBgColor = getStatusBgColor(currentStatus?.status);

  const [selectOpen, setSelectOpen] = React.useState(false);

  const handleValidateClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.nativeEvent.stopPropagation();
    e.nativeEvent.preventDefault();
    if (value && onValidate && !isValidating) {
      onValidate(value);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (isValidating && open) {
      return;
    }
    setSelectOpen(open);
  };

  const showValidateArea = onValidate && value && !disabled;

  return (
    <Select
      value={value}
      onValueChange={onChange}
      disabled={disabled}
      open={selectOpen}
      onOpenChange={handleOpenChange}
    >
      <SelectTrigger className={cn("w-full", statusBgColor)}>
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <SelectValue placeholder={placeholder}>
            {currentModel?.display_name ?? currentModel?.name ?? value}
          </SelectValue>
        </div>
        {showValidateArea && (
          <div
            className={cn(
              "flex items-center justify-center p-1 rounded transition-colors cursor-pointer select-none",
              "hover:bg-accent/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              isValidating && "animate-spin",
              currentStatus?.status === "available" && "text-green-500 hover:text-green-600",
              currentStatus?.status === "unavailable" && "text-red-500 hover:text-red-600",
              currentStatus?.status === "error" && "text-yellow-500 hover:text-yellow-600",
              !currentStatus?.status && "text-muted-foreground"
            )}
            onClick={handleValidateClick}
            onPointerDown={(e) => e.stopPropagation()}
            title={currentStatus?.message ?? "点击验证模型"}
          >
            {isValidating ? (
              <Loader2 className="h-4 w-4" />
            ) : statusIcon ? (
              <span className="text-sm font-bold">{statusIcon}</span>
            ) : (
              <span className="text-xs px-1">验证</span>
            )}
          </div>
        )}
      </SelectTrigger>
      <SelectContent>
        {groups.map((group) => (
          <SelectGroup key={group.provider}>
            <SelectLabel>{group.provider}</SelectLabel>
            {group.models.map((model) => {
              const status = modelStatuses[model.name];
              const itemStatusIcon = getStatusIcon(status?.status);
              const itemStatusColor = getStatusColor(status?.status);
              return (
                <SelectItem key={model.name} value={model.name}>
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="truncate">{model.display_name}</span>
                    {itemStatusIcon && (
                      <span
                        className={`shrink-0 text-xs font-bold ${itemStatusColor}`}
                        title={status?.message ?? ""}
                      >
                        {itemStatusIcon}
                      </span>
                    )}
                  </div>
                </SelectItem>
              );
            })}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}
