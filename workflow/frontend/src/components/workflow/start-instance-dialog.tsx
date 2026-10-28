"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  FileText,
  Loader2,
  PlayCircle,
  Workflow,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { FormSchema } from "@/lib/types";
import {
  findFormByPath,
  formValuesFromVariables,
  initialFormValues,
  missingRequiredFields,
  parseFormSchema,
} from "@/lib/forms";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FormRenderer } from "@/components/workflow/form-renderer";

function defaultBusinessId(code?: string) {
  const stamp = new Date()
    .toISOString()
    .replace(/[-:TZ.]/g, "")
    .slice(2, 14);
  return `${code ? code.toUpperCase() : "WF"}-${stamp}`;
}

export function StartInstanceDialog({
  open,
  onOpenChange,
  onStarted,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStarted?: (instanceId: number) => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useSession();
  const [flowCode, setFlowCode] = useState("");
  const [businessId, setBusinessId] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [extra, setExtra] = useState("");

  const definitionsQuery = useQuery({
    queryKey: ["definitions", "start-options"],
    queryFn: () => api.definitions.list({ page: 1, size: 200, isPublish: 1 }),
    enabled: open,
    staleTime: 30_000,
  });

  const options = useMemo(
    () => (definitionsQuery.data?.items || []).filter((item) => item.activity_status === 1),
    [definitionsQuery.data],
  );

  const selected = useMemo(
    () => options.find((item) => item.flow_code === flowCode) || null,
    [options, flowCode],
  );

  const designerQuery = useQuery({
    queryKey: ["designer", "start", selected?.id],
    queryFn: () => api.designer.query(selected!.id),
    enabled: open && Boolean(selected?.id),
  });

  const formsQuery = useQuery({
    queryKey: ["forms", "published"],
    queryFn: api.designer.publishedForms,
    enabled: open,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (!open) return;
    setFlowCode("");
    setBusinessId(defaultBusinessId());
    setValues({});
    setExtra("");
  }, [open]);

  const startNode = designerQuery.data?.nodeList?.find((node) => node.nodeType === 0);
  const formPath = startNode?.formPath || selected?.form_path || null;
  const boundForm = findFormByPath(formsQuery.data, formPath);
  const schema = useMemo<FormSchema | null>(() => {
    if (!boundForm?.form_content) return null;
    const parsed = parseFormSchema(boundForm.form_content);
    return parsed.fields.length ? parsed : null;
  }, [boundForm]);

  useEffect(() => {
    setValues((current) => initialFormValues(schema, current));
  }, [schema]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!selected) throw new ApiError("请选择要发起的流程", 400);
      const missing = missingRequiredFields(schema, values);
      if (missing.length) {
        throw new ApiError(`请填写必填项：${missing.join("、")}`, 400);
      }
      let extraVars: Record<string, unknown> = {};
      if (extra.trim()) {
        try {
          const parsed = JSON.parse(extra);
          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            throw new Error("not object");
          }
          extraVars = parsed as Record<string, unknown>;
        } catch {
          throw new ApiError("附加变量必须是合法的 JSON 对象", 400);
        }
      }
      const variables = formValuesFromVariables({ ...extraVars, ...values });
      return api.instances.start({
        flow_code: selected.flow_code,
        business_id: businessId.trim() || defaultBusinessId(selected.flow_code),
        variables: { ...extraVars, ...variables, formData: variables },
        handler: user.handler,
      });
    },
    onSuccess: (instance) => {
      queryClient.invalidateQueries({ queryKey: ["instances"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
      toast.success("流程已发起，进入首个审批节点");
      onOpenChange(false);
      if (onStarted) onStarted(instance.id);
      else router.push(`/instances/${instance.id}`);
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "发起失败，请稍后重试"),
  });

  const loadingDefinition = Boolean(selected) && designerQuery.isLoading;
  const disabled = !selected || mutation.isPending || loadingDefinition;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100vh-2rem)] max-w-[820px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <PlayCircle className="h-4 w-4" />
            </span>
            发起流程
          </DialogTitle>
          <DialogDescription>
            选择已发布且未挂起的流程，填写业务编号与表单后启动实例。首个节点会立即进入审批。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-5 py-1">
          <div className="grid gap-1.5">
            <Label>
              流程定义 <span className="text-destructive">*</span>
            </Label>
            {definitionsQuery.isLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : (
              <Select
                value={flowCode}
                onValueChange={(code) => {
                  setFlowCode(code);
                  setBusinessId(defaultBusinessId(code));
                  setValues({});
                  setExtra("");
                }}
                options={options.map((definition) => ({
                  value: definition.flow_code,
                  label: `${definition.flow_name} · ${definition.flow_code} v${definition.version}`,
                }))}
                placeholder={options.length ? "选择流程…" : "暂无已发布流程"}
                disabled={!options.length}
              />
            )}
            {!definitionsQuery.isLoading && !options.length && (
              <p className="text-[11px] text-amber-600">
                还没有可发起的流程，请先在流程定义页发布并确认未挂起。
              </p>
            )}
          </div>

          {selected && (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-muted/25 px-3.5 py-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-card text-primary shadow-[0_1px_2px_rgba(16,24,40,0.06)]">
                <Workflow className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium">{selected.flow_name}</p>
                <p className="text-[10.5px] text-muted-foreground">
                  版本 v{selected.version}
                  {selected.category ? ` · ${selected.category}` : ""} · 发起人 {user.name}
                </p>
              </div>
            </div>
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="business-id">
              业务编号 <span className="text-destructive">*</span>
            </Label>
            <Input
              id="business-id"
              value={businessId}
              onChange={(event) => setBusinessId(event.target.value)}
              placeholder="例如：LEAVE-20261023-001"
              className="font-mono text-[13px]"
            />
            <p className="text-[11px] text-muted-foreground">
              业务编号用于在实例列表中检索；留空时自动生成。
            </p>
          </div>

          {selected && (
            <div className="rounded-xl border border-border">
              <div className="flex items-center gap-2 border-b border-border px-3.5 py-2.5">
                <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-[12px] font-medium">业务表单</p>
                {boundForm ? (
                  <Badge variant="success" className="ml-auto">
                    {boundForm.form_name} v{boundForm.version}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="ml-auto">
                    未绑定表单
                  </Badge>
                )}
              </div>
              <div className={cn("p-4", loadingDefinition && "opacity-60")}>
                {loadingDefinition ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Skeleton className="h-9 w-full" />
                    <Skeleton className="h-9 w-full" />
                    <Skeleton className="h-20 w-full sm:col-span-2" />
                  </div>
                ) : schema ? (
                  <FormRenderer schema={schema} values={values} onChange={setValues} />
                ) : (
                  <p className="py-3 text-center text-[12px] text-muted-foreground">
                    {formPath
                      ? "未找到与该流程绑定的已发布表单，可直接使用下方附加变量发起。"
                      : "该流程没有绑定业务表单，可直接发起，或使用下方附加变量传入业务参数。"}
                  </p>
                )}
              </div>
            </div>
          )}

          <details className="group rounded-xl border border-border bg-muted/20 px-3.5 py-3">
            <summary className="cursor-pointer list-none text-[12px] font-medium text-muted-foreground transition hover:text-foreground [&::-webkit-details-marker]:hidden">
              高级：附加流程变量（JSON）
            </summary>
            <div className="mt-3 space-y-2">
              <Textarea
                value={extra}
                onChange={(event) => setExtra(event.target.value)}
                placeholder={'{\n  "amount": 6800,\n  "department": "d01"\n}'}
                className="min-h-[92px] font-mono text-[12px]"
              />
              <p className="text-[10.5px] leading-relaxed text-muted-foreground">
                变量会与表单值合并后写入实例快照，可用于网关条件表达式，例如
                <code className="mx-1 rounded bg-muted px-1 py-0.5 font-mono text-[10px]">
                  le@@amount|5000
                </code>
                。
              </p>
            </div>
          </details>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
            取消
          </Button>
          <Button disabled={disabled} onClick={() => mutation.mutate()}>
            {mutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <PlayCircle className="h-4 w-4" />
            )}
            {mutation.isPending ? "发起中…" : "发起流程"}
            {!mutation.isPending && <ArrowRight className="h-4 w-4" />}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
