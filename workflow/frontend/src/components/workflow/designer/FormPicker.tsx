"use client";

import { FileText, Search } from "lucide-react";
import { useState } from "react";
import type { FormDefinition } from "@/lib/types";
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
import { cn } from "@/lib/utils";

export function FormPicker({
  open,
  forms,
  value,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  forms: FormDefinition[];
  value: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: (value: string | null) => void;
}) {
  const [keyword, setKeyword] = useState("");
  const rows = forms.filter(
    (form) =>
      !keyword ||
      form.form_name.includes(keyword) ||
      form.form_code.toLowerCase().includes(keyword.toLowerCase()),
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[500px]">
        <DialogHeader>
          <DialogTitle>选择业务表单</DialogTitle>
          <DialogDescription>
            只列出已发布的表单。表单由表单中心维护，流程节点只保存表单路径。
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索表单名称或编码…"
            className="pl-8"
          />
        </div>

        <div className="max-h-[300px] overflow-y-auto rounded-xl border border-border">
          <button
            type="button"
            onClick={() => {
              onConfirm(null);
              onOpenChange(false);
            }}
            className={cn(
              "flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left transition hover:bg-accent",
              !value && "bg-primary/[0.04]",
            )}
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <FileText className="h-4 w-4" />
            </span>
            <span className="flex-1">
              <span className="block text-[13px] font-medium">不使用表单</span>
              <span className="block text-[11px] text-muted-foreground">节点只展示审批操作</span>
            </span>
            {!value && <span className="h-2 w-2 rounded-full bg-primary" />}
          </button>
          {rows.length === 0 ? (
            <p className="px-4 py-8 text-center text-[12px] text-muted-foreground">
              没有已发布的表单
            </p>
          ) : (
            rows.map((form) => {
              const path = form.form_path || `${form.form_code}:${form.version}`;
              const active = value === path;
              return (
                <button
                  key={form.id}
                  type="button"
                  onClick={() => {
                    onConfirm(path);
                    onOpenChange(false);
                  }}
                  className={cn(
                    "flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left transition last:border-b-0 hover:bg-accent",
                    active && "bg-primary/[0.04]",
                  )}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <FileText className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium">{form.form_name}</span>
                    <span className="block truncate font-mono text-[11px] text-muted-foreground">
                      {path}
                    </span>
                  </span>
                  {active && <span className="h-2 w-2 rounded-full bg-primary" />}
                </button>
              );
            })
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
