"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  Download,
  PauseCircle,
  PlayCircle,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Definition } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function DefinitionActionsDialog({
  definition,
  open,
  onOpenChange,
}: {
  definition: Definition | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (open) setConfirmDelete(false);
  }, [open, definition?.id]);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["definitions"] });
    queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
  }

  const copyMutation = useMutation({
    mutationFn: () => api.definitions.copy(definition!.id),
    onSuccess: (clone) => {
      invalidate();
      toast.success(`已复制为 v${clone.version}`);
      onOpenChange(false);
    },
    onError: (error: unknown) => toast.error(error instanceof ApiError ? error.message : "复制失败"),
  });

  const activityMutation = useMutation({
    mutationFn: () =>
      definition!.activity_status === 1
        ? api.definitions.suspend(definition!.id)
        : api.definitions.activate(definition!.id),
    onSuccess: () => {
      invalidate();
      toast.success(definition!.activity_status === 1 ? "流程已挂起" : "流程已激活");
      onOpenChange(false);
    },
    onError: (error: unknown) => toast.error(error instanceof ApiError ? error.message : "操作失败"),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.definitions.remove(definition!.id),
    onSuccess: () => {
      invalidate();
      toast.success("流程定义已删除");
      onOpenChange(false);
    },
    onError: (error: unknown) => toast.error(error instanceof ApiError ? error.message : "删除失败"),
  });

  async function exportJson() {
    if (!definition) return;
    try {
      const payload = await api.definitions.exportJson(definition.id);
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${definition.flow_code}-v${definition.version}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success("导出成功");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "导出失败");
    }
  }

  const busy = copyMutation.isPending || activityMutation.isPending || deleteMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[440px]">
        <DialogHeader>
          <DialogTitle>流程操作</DialogTitle>
          <DialogDescription>
            {definition ? `${definition.flow_name} · v${definition.version}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="divide-y divide-border overflow-hidden rounded-xl border border-border">
          <ActionRow
            icon={Copy}
            title="复制为新版本"
            description="保留节点与跳转，生成一个未发布的版本"
            onClick={() => copyMutation.mutate()}
            disabled={busy}
          />
          <ActionRow
            icon={Download}
            title="导出 JSON"
            description="导出标准 DefJson，可再次导入或迁移"
            onClick={() => void exportJson()}
            disabled={busy}
          />
          <ActionRow
            icon={definition?.activity_status === 1 ? PauseCircle : PlayCircle}
            title={definition?.activity_status === 1 ? "挂起流程" : "激活流程"}
            description={
              definition?.activity_status === 1
                ? "挂起后不能再发起新的实例"
                : "恢复发起与流转能力"
            }
            onClick={() => activityMutation.mutate()}
            disabled={busy}
          />
        </div>

        <div className="rounded-xl border border-rose-200/70 bg-rose-50/60 p-3.5">
          {confirmDelete ? (
            <div className="space-y-3">
              <div className="flex items-start gap-2">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
                <p className="text-[12px] leading-relaxed text-rose-700">
                  删除后不可恢复。已产生实例的流程定义会被后端拒绝删除，此时请使用挂起。
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
                  取消
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? "删除中…" : "确认删除"}
                </Button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="flex w-full items-center gap-2 text-left"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 className="h-4 w-4 text-rose-600" />
              <span className="flex-1">
                <span className="block text-[13px] font-medium text-rose-700">删除流程定义</span>
                <span className="block text-[11px] text-rose-600/80">
                  软删除，需要二次确认
                </span>
              </span>
            </button>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ActionRow({
  icon: Icon,
  title,
  description,
  onClick,
  disabled,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex w-full items-center gap-3 bg-card px-4 py-3 text-left transition hover:bg-accent disabled:opacity-50"
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <span className="flex-1">
        <span className="block text-[13px] font-medium">{title}</span>
        <span className="block text-[11px] text-muted-foreground">{description}</span>
      </span>
    </button>
  );
}
