"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Building2, Search, ShieldCheck, UserRound, Users } from "lucide-react";
import { api } from "@/lib/api";
import type { HandlerOption } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn, initials } from "@/lib/utils";

const GROUPS = [
  { value: "用户", label: "用户", icon: UserRound },
  { value: "角色", label: "角色", icon: ShieldCheck },
  { value: "部门", label: "部门", icon: Building2 },
];

export function HandlerPicker({
  open,
  value,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  value: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: (value: string) => void;
}) {
  const handlersQuery = useQuery({
    queryKey: ["meta", "handlers"],
    queryFn: api.meta.handlers,
    staleTime: 5 * 60 * 1000,
  });
  const [tab, setTab] = useState("用户");
  const [keyword, setKeyword] = useState("");
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    setKeyword("");
    setSelected(value ? value.split("@@").filter(Boolean) : []);
  }, [open, value]);

  const options = useMemo(() => {
    const rows = handlersQuery.data || [];
    return rows.filter((item) => {
      const group = item.type || item.groupName || "用户";
      const groupMatch = group.includes(tab);
      const keywordMatch =
        !keyword ||
        item.handlerName.includes(keyword) ||
        item.storageId.toLowerCase().includes(keyword.toLowerCase());
      return groupMatch && keywordMatch;
    });
  }, [handlersQuery.data, keyword, tab]);

  function toggle(code: string) {
    setSelected((current) =>
      current.includes(code) ? current.filter((item) => item !== code) : [...current, code],
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Users className="h-4 w-4" />
            </span>
            选择办理人
          </DialogTitle>
          <DialogDescription>
            支持用户、角色、部门混合选择，保存时使用 <code className="text-[11px]">@@</code>{" "}
            连接。未配置时默认回退给发起人。
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="flex rounded-lg border border-border bg-muted/40 p-1">
              {GROUPS.map((group) => {
                const Icon = group.icon;
                return (
                  <button
                    key={group.value}
                    type="button"
                    onClick={() => setTab(group.value)}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] transition",
                      tab === group.value
                        ? "bg-card font-medium text-primary shadow-sm"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {group.label}
                  </button>
                );
              })}
            </div>
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索名称或编码…"
                className="h-9 pl-8"
              />
            </div>
          </div>

          <div className="h-[280px] overflow-y-auto rounded-xl border border-border">
            {handlersQuery.isLoading ? (
              <div className="p-4 text-center text-[12px] text-muted-foreground">加载中…</div>
            ) : options.length === 0 ? (
              <div className="p-8 text-center text-[12px] text-muted-foreground">
                没有匹配的办理人
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {options.map((item) => {
                  const checked = selected.includes(item.storageId);
                  return (
                    <li key={item.storageId}>
                      <button
                        type="button"
                        onClick={() => toggle(item.storageId)}
                        className={cn(
                          "flex w-full items-center gap-3 px-4 py-2.5 text-left transition",
                          checked ? "bg-primary/[0.045]" : "hover:bg-accent/70",
                        )}
                      >
                        <span
                          className={cn(
                            "flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-medium",
                            checked
                              ? "bg-primary text-white"
                              : "bg-muted text-muted-foreground",
                          )}
                        >
                          {initials(item.handlerName)}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">
                            {item.handlerName}
                          </span>
                          <span className="block truncate text-[11px] text-muted-foreground">
                            {item.groupName} · {item.storageId}
                          </span>
                        </span>
                        <span
                          className={cn(
                            "flex h-4 w-4 items-center justify-center rounded border text-[10px]",
                            checked
                              ? "border-primary bg-primary text-white"
                              : "border-input bg-card text-transparent",
                          )}
                        >
                          ✓
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {selected.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {selected.map((code) => {
                const found = (handlersQuery.data || []).find((item) => item.storageId === code);
                return (
                  <span
                    key={code}
                    className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/5 px-2 py-0.5 text-[11px] text-primary"
                  >
                    {found?.handlerName || code}
                    <button
                      type="button"
                      className="opacity-60 hover:opacity-100"
                      onClick={() => toggle(code)}
                    >
                      ×
                    </button>
                  </span>
                );
              })}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={() => {
              onConfirm(selected.join("@@"));
              onOpenChange(false);
            }}
          >
            确定选择（{selected.length}）
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function handlerNames(value: string, handlers: HandlerOption[]): string[] {
  if (!value) return [];
  return value
    .split("@@")
    .filter(Boolean)
    .map((code) => handlers.find((item) => item.storageId === code)?.handlerName || code);
}
