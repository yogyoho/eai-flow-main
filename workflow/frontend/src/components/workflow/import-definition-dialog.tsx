"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileJson, Upload } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export function ImportDefinitionDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [filename, setFilename] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = JSON.parse(text) as Record<string, unknown>;
      return api.definitions.importJson(payload);
    },
    onSuccess: (definition) => {
      queryClient.invalidateQueries({ queryKey: ["definitions"] });
      queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
      toast.success(`已导入「${definition.flow_name}」v${definition.version}`);
      setText("");
      setFilename("");
      onOpenChange(false);
    },
    onError: (error: unknown) => {
      if (error instanceof SyntaxError) {
        toast.error("JSON 解析失败，请检查格式");
      } else {
        toast.error(error instanceof ApiError ? error.message : "导入失败");
      }
    },
  });

  async function readFile(file?: File | null) {
    if (!file) return;
    if (!file.name.endsWith(".json")) {
      toast.error("请选择 .json 文件");
      return;
    }
    setText(await file.text());
    setFilename(file.name);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[620px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-50 text-violet-600">
              <FileJson className="h-4 w-4" />
            </span>
            导入流程定义
          </DialogTitle>
          <DialogDescription>
            粘贴 warm-flow 导出的 DefJson，或拖入 JSON 文件。导入会生成一个新的版本。
          </DialogDescription>
        </DialogHeader>

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void readFile(event.dataTransfer.files?.[0]);
          }}
          className={cn(
            "flex items-center gap-3 rounded-xl border border-dashed p-4 transition",
            dragging ? "border-primary bg-primary/5" : "border-border bg-muted/30",
          )}
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card">
            <Upload className="h-4 w-4 text-muted-foreground" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium">
              {filename || "拖入 JSON 文件，或点击选择"}
            </p>
            <p className="text-[11px] text-muted-foreground">仅解析 flowCode / nodeList 契约</p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>
            选择文件
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => void readFile(event.target.files?.[0])}
          />
        </div>

        <Textarea
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setFilename("");
          }}
          placeholder={'{\n  "flowCode": "leave_apply",\n  "flowName": "请假审批",\n  "nodeList": [ ... ]\n}'}
          className="h-56 font-mono text-[12px] leading-relaxed"
        />

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={!text.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "导入中…" : "导入并创建版本"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
