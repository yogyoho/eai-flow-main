"use client";

import { Loader2, X } from "lucide-react";
import React, { useEffect, useState } from "react";

// EAI-CUSTOM: 部门级访问权限选择器(spec 2026-09-05-kb-dept-access-picker-design)
// admin: 内联勾选面板(max-h-40 滚动)+ 下方标签(× 移除);普通用户(readOnly):只读标签。
// 部门列表组件内懒加载 deptApi.list(GET /departments 仅需登录,普通用户可调)。
import { deptApi } from "@/extensions/api";
import type { Department } from "@/extensions/types";
import { cn } from "@/lib/utils";

export function DeptAccessPicker({
  selectedIds,
  onChange,
  readOnly = false,
}: {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  readOnly?: boolean;
}) {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    deptApi
      .list({ limit: 500 })
      .then((res) => {
        if (!cancelled) setDepartments(res.departments ?? []);
      })
      .catch(() => {
        if (!cancelled) setDepartments([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const nameOf = (id: string) =>
    departments.find((d) => d.id === id)?.name ?? id;

  const toggle = (id: string) =>
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id],
    );

  if (loading) {
    return <Loader2 className="text-muted-foreground h-4 w-4 animate-spin" />;
  }

  return (
    <div className="space-y-2">
      {!readOnly && (
        <div className="border-border max-h-40 overflow-y-auto rounded-lg border p-2">
          {departments.length === 0 ? (
            <p className="text-muted-foreground text-xs">暂无可选部门</p>
          ) : (
            departments.map((d) => (
              <label
                key={d.id}
                className="hover:bg-accent flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(d.id)}
                  onChange={() => toggle(d.id)}
                />
                {d.name}
              </label>
            ))
          )}
        </div>
      )}

      {selectedIds.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedIds.map((id) => (
            <span
              key={id}
              className={cn(
                "bg-primary/10 text-primary inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs",
              )}
            >
              {nameOf(id)}
              {!readOnly && (
                <button
                  type="button"
                  aria-label={`移除 ${nameOf(id)}`}
                  onClick={() => onChange(selectedIds.filter((x) => x !== id))}
                  className="hover:text-destructive"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {readOnly && selectedIds.length === 0 && (
        <p className="text-muted-foreground text-xs">你尚未加入任何部门</p>
      )}
    </div>
  );
}
