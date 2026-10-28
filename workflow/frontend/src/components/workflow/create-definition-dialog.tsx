"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Sparkles } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function slug(): string {
  return `flow_${Math.random().toString(36).slice(2, 8)}`;
}

export function CreateDefinitionDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [category, setCategory] = useState("");

  useEffect(() => {
    if (open) {
      setName("");
      setCode(slug());
      setCategory("");
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: () =>
      api.definitions.create({
        flow_name: name.trim(),
        flow_code: code.trim(),
        category: category.trim() || null,
      }),
    onSuccess: (definition) => {
      queryClient.invalidateQueries({ queryKey: ["definitions"] });
      queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
      toast.success("流程已创建，进入设计器");
      onOpenChange(false);
      router.push(`/design/${definition.id}`);
    },
    onError: (error: unknown) => {
      toast.error(error instanceof ApiError ? error.message : "创建失败");
    },
  });

  const disabled = !name.trim() || !code.trim() || mutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sparkles className="h-4 w-4" />
            </span>
            新建流程
          </DialogTitle>
          <DialogDescription>
            先创建流程元数据，随后在设计器中绘制节点与跳转，发布后即可发起实例。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-1">
          <div className="grid gap-1.5">
            <Label htmlFor="flow-name">
              流程名称 <span className="text-destructive">*</span>
            </Label>
            <Input
              id="flow-name"
              autoFocus
              placeholder="例如：差旅报销审批"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="flow-code">
                流程编码 <span className="text-destructive">*</span>
              </Label>
              <Input
                id="flow-code"
                placeholder="leave_apply"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                className="font-mono text-[13px]"
              />
              <p className="text-[11px] text-muted-foreground">同一编码的多个版本共享发布线。</p>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="flow-category">分类</Label>
              <Input
                id="flow-category"
                placeholder="人事 / 财务 / 采购"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={disabled} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "创建中…" : "创建并设计"}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
