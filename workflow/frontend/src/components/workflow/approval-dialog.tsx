"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  Check,
  CircleAlert,
  GitPullRequestArrow,
  Loader2,
  Undo2,
  UserPlus,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useUserDirectory } from "@/lib/directory";
import { formValuesFromVariables, initialFormValues } from "@/lib/forms";
import type { FormSchema, HisTask } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { FormRenderer } from "@/components/workflow/form-renderer";
import { HandlerPicker } from "@/components/workflow/designer/HandlerPicker";
import { StatusBadge } from "@/components/status-badge";
import { cn, formatDate, parseJson } from "@/lib/utils";

type HandlerMode = "transfer" | "depute" | "signature" | null;

export function ApprovalDialog({
  open,
  taskId,
  hisId,
  onOpenChange,
  onDone,
}: {
  open: boolean;
  taskId: number | null;
  hisId: number | null;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}) {
  const { user } = useSession();
  const directory = useUserDirectory();
  const readOnly = Boolean(hisId);

  const loadQuery = useQuery({
    queryKey: [hisId ? "his-load" : "task-load", hisId || taskId],
    queryFn: () => (hisId ? api.designer.loadHis(hisId) : api.designer.loadTask(taskId as number)),
    enabled: open && Boolean(hisId || taskId),
  });

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [message, setMessage] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<string>("last");
  const [handlerMode, setHandlerMode] = useState<HandlerMode>(null);

  useEffect(() => {
    if (!open) {
      setValues({});
      setMessage("");
      setRejectOpen(false);
      setRejectTarget("last");
      setHandlerMode(null);
    }
  }, [open]);

  useEffect(() => {
    const loaded = loadQuery.data;
    if (!loaded) return;
    setValues(formValuesFromVariables(loaded.data?.variables));
    setMessage("");
  }, [loadQuery.data]);

  const task = loadQuery.data?.data?.task;
  const instance = loadQuery.data?.data?.instance;
  const node = loadQuery.data?.data?.node;
  const resubmitTask = Boolean(!readOnly && task && (task.node_code === "start" || task.node_type === 0));
  const hisTask = (
    loadQuery.data?.data as unknown as { hisTask?: HisTask } | undefined
  )?.hisTask;
  const schema = useMemo<FormSchema | null>(() => {
    const fromForm = loadQuery.data?.form?.schema;
    if (fromForm?.fields?.length) return fromForm;
    const parsed = parseJson<FormSchema>(loadQuery.data?.formContent, { fields: [] });
    return parsed.fields?.length ? parsed : null;
  }, [loadQuery.data]);

  // Make the first select option (and switch defaults) real form state so
  // required validation matches what the user sees.
  useEffect(() => {
    if (readOnly) return;
    setValues((current) => initialFormValues(schema, current));
  }, [schema, readOnly]);

  const previousNodes = useMemo(() => {
    const chart = task?.chart || instance?.def_json;
    const current = task?.node_code;
    if (!chart?.nodeList?.length || !current) return [];

    const byCode = new Map(chart.nodeList.map((item) => [item.nodeCode, item]));
    const predecessors = new Map<string, string[]>();
    for (const item of chart.nodeList) {
      for (const skip of item.skipList || []) {
        if (skip.skipType === "REJECT" || !skip.nextNodeCode) continue;
        const list = predecessors.get(skip.nextNodeCode) || [];
        if (!list.includes(item.nodeCode)) list.push(item.nodeCode);
        predecessors.set(skip.nextNodeCode, list);
      }
    }

    // Walk back through gateways (exclusive/parallel/inclusive) so the user can
    // pick a real approval node rather than an unroutable gateway.
    const rows: { code: string; label: string }[] = [];
    const seen = new Set<string>([current]);
    const walk = (code: string, depth: number) => {
      if (depth > 16) return;
      for (const prev of predecessors.get(code) || []) {
        if (seen.has(prev)) continue;
        seen.add(prev);
        const item = byCode.get(prev);
        if (!item) continue;
        if (item.nodeType === 3 || item.nodeType === 4 || item.nodeType === 5) {
          walk(prev, depth + 1);
        } else if (item.nodeType === 1) {
          rows.push({ code: prev, label: item.nodeName || prev });
        }
      }
    };
    walk(current, 0);
    return rows;
  }, [task, instance]);

  function invalidate() {
    onDone();
  }

  const approveMutation = useMutation({
    mutationFn: () => {
      const variables = formValuesFromVariables(values);
      return api.tasks.approve(taskId as number, {
        message,
        variables: { ...variables, formData: variables },
      });
    },
    onSuccess: () => {
      toast.success(resubmitTask ? "已重新提交，流程从第一步继续" : "已通过，流程继续流转");
      onOpenChange(false);
      invalidate();
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "审批失败"),
  });

  const rejectMutation = useMutation({
    mutationFn: () => {
      const variables = formValuesFromVariables(values);
      if (rejectTarget === "last") {
        return api.tasks.rejectLast(taskId as number, {
          message,
          variables: { ...variables, formData: variables },
        });
      }
      return api.tasks.reject(taskId as number, {
        message,
        variables: { ...variables, formData: variables },
        node_code: rejectTarget,
      });
    },
    onSuccess: () => {
      toast.success("已退回");
      onOpenChange(false);
      invalidate();
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "退回失败"),
  });

  const handlerMutation = useMutation({
    mutationFn: ({ mode, codes }: { mode: HandlerMode; codes: string[] }) => {
      if (mode === "transfer") {
        return api.tasks.transfer(taskId as number, codes, message);
      }
      if (mode === "depute") {
        return api.tasks.depute(taskId as number, codes, message);
      }
      return api.tasks.addSignature(taskId as number, codes);
    },
    onSuccess: (_data, variables) => {
      toast.success(
        variables.mode === "transfer" ? "已转办" : variables.mode === "depute" ? "已委派" : "已加签",
      );
      setHandlerMode(null);
      onOpenChange(false);
      invalidate();
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "操作失败"),
  });

  const loading = loadQuery.isLoading;
  const busy = approveMutation.isPending || rejectMutation.isPending;

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-[860px] p-0">
          <DialogHeader className="border-b border-border px-6 py-4">
            <div className="flex items-center gap-2">
              <DialogTitle className="text-[16px]">
                {readOnly ? "审批记录" : "审批办理"}
              </DialogTitle>
              {instance?.flow_status && (
                <StatusBadge
                  tone={instance.flow_status_tone}
                  label={instance.flow_status_label || instance.flow_status}
                />
              )}
              {readOnly && <Badge variant="outline">只读</Badge>}
            </div>
            <DialogDescription>
              {instance?.flow_name || task?.flow_name || "流程实例"}
              {instance?.business_id ? ` · ${instance.business_id}` : ""}
            </DialogDescription>
          </DialogHeader>

          {loading ? (
            <div className="space-y-4 p-6">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : loadQuery.isError ? (
            <div className="p-10 text-center text-[13px] text-muted-foreground">
              加载失败，请关闭后重试
            </div>
          ) : (
            <div className="grid max-h-[calc(100vh-260px)] grid-cols-1 overflow-y-auto md:grid-cols-[1fr_248px]">
              <div className="space-y-5 p-6">
                <div className="flex items-start gap-3 rounded-xl border border-border bg-muted/20 p-3.5">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <GitPullRequestArrow className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium">
                      {task?.node_name || node?.nodeName || (readOnly ? "历史节点" : "审批节点")}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {readOnly
                        ? `办理人 ${directory.name(hisTask?.approver)} · ${hisTask?.cooperate_label || "审批"}`
                        : resubmitTask
                          ? `待办 #${taskId} · 资料已被退回，请修改后重新提交`
                          : `待办 #${taskId} · 请核对表单信息后处理`}
                    </p>
                  </div>
                </div>

                <FormRenderer
                  schema={schema}
                  values={values}
                  onChange={setValues}
                  readOnly={readOnly}
                />

                {readOnly ? (
                  <div className="rounded-xl border border-border bg-muted/20 p-4">
                    <p className="text-[11px] font-semibold text-muted-foreground">审批意见</p>
                    <p className="mt-1 text-[13px]">{hisTask?.message || "无"}</p>
                  </div>
                ) : (
                  <div className="grid gap-1.5">
                    <label className="text-[11.5px] font-medium">
                      {resubmitTask ? "重新提交说明" : "审批意见"}
                    </label>
                    <Textarea
                      value={message}
                      onChange={(event) => setMessage(event.target.value)}
                      placeholder={resubmitTask ? "可填写补充说明…" : "可填写通过 / 退回原因…"}
                      className="min-h-[72px]"
                    />
                  </div>
                )}

                {!readOnly && rejectOpen && !resubmitTask && (
                  <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4">
                    <div className="flex items-center gap-2 text-[12px] font-medium text-rose-700">
                      <Undo2 className="h-3.5 w-3.5" />
                      选择退回目标
                    </div>
                    <div className="mt-3 grid gap-2">
                      <label className="flex cursor-pointer items-center gap-2 text-[12px]">
                        <input
                          type="radio"
                          checked={rejectTarget === "last"}
                          onChange={() => setRejectTarget("last")}
                          className="accent-rose-600"
                        />
                        退回上一节点（推荐）
                      </label>
                      {previousNodes.map((item) => (
                        <label
                          key={item.code}
                          className="flex cursor-pointer items-center gap-2 text-[12px]"
                        >
                          <input
                            type="radio"
                            checked={rejectTarget === item.code}
                            onChange={() => setRejectTarget(item.code)}
                            className="accent-rose-600"
                          />
                          退回到「{item.label}」
                          <span className="font-mono text-[10px] text-muted-foreground">
                            {item.code}
                          </span>
                        </label>
                      ))}
                      {!previousNodes.length && (
                        <p className="text-[11px] text-rose-600/80">
                          当前节点之前没有可退回的审批节点，退回不可用。
                        </p>
                      )}
                    </div>
                    <p className="mt-3 text-[10.5px] leading-relaxed text-rose-600/80">
                      退回后当前节点待办会关闭，并重新生成目标节点任务。会签节点可按比例配置。
                    </p>
                  </div>
                )}
              </div>

              <aside className="border-t border-border bg-muted/20 p-5 md:border-l md:border-t-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  流程上下文
                </p>
                <dl className="mt-3 space-y-3 text-[11.5px]">
                  <Info label="发起人" value={directory.name(instance?.create_by)} />
                  <Info label="发起时间" value={formatDate(instance?.create_time)} />
                  <Info label="当前节点" value={task?.node_name || instance?.node_name || "—"} />
                  <Info label="业务编号" value={instance?.business_id || "—"} />
                  <Info label="流程状态" value={instance?.flow_status_label || "—"} />
                </dl>

                {task?.assignees?.length ? (
                  <div className="mt-5">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                      办理人
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {task.assignees.map((handler) => (
                        <Badge key={handler} variant="outline">
                          {directory.name(handler)}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="mt-5 rounded-lg border border-border bg-card p-3">
                  <p className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
                    <CircleAlert className="h-3 w-3" />
                    审批结果将写入历史任务，可在实例详情查看完整时间线。
                  </p>
                </div>
              </aside>
            </div>
          )}

          {!readOnly && !loading && !loadQuery.isError && (
            <DialogFooter className="border-t border-border px-6 py-4">
              {!resubmitTask ? (
                <div className="mr-auto flex flex-wrap items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => setHandlerMode("transfer")}
                  >
                    <ArrowLeftRight className="h-3.5 w-3.5" />
                    转办
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => setHandlerMode("depute")}
                  >
                    <Users className="h-3.5 w-3.5" />
                    委派
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => setHandlerMode("signature")}
                  >
                    <UserPlus className="h-3.5 w-3.5" />
                    加签
                  </Button>
                </div>
              ) : (
                <div className="mr-auto text-[11px] text-muted-foreground">
                  原审批单号和流程实例保留
                </div>
              )}
              {resubmitTask ? (
                <Button onClick={() => approveMutation.mutate()} disabled={busy}>
                  {approveMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                  重新提交
                </Button>
              ) : rejectOpen ? (
                <>
                  <Button variant="ghost" onClick={() => setRejectOpen(false)}>
                    取消退回
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => rejectMutation.mutate()}
                    disabled={busy}
                  >
                    {rejectMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Undo2 className="h-4 w-4" />
                    )}
                    确认退回
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    className="border-rose-200 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                    onClick={() => {
                      setRejectTarget("last");
                      setRejectOpen(true);
                    }}
                    disabled={busy}
                  >
                    <Undo2 className="h-4 w-4" />
                    退回
                  </Button>
                  <Button onClick={() => approveMutation.mutate()} disabled={busy}>
                    {approveMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Check className="h-4 w-4" />
                    )}
                    通过
                  </Button>
                </>
              )}
            </DialogFooter>
          )}

          {readOnly && (
            <DialogFooter className="border-t border-border px-6 py-4">
              <Button variant="secondary" onClick={() => onOpenChange(false)}>
                关闭
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      <HandlerPicker
        open={Boolean(handlerMode)}
        value=""
        onOpenChange={(next) => {
          if (!next) setHandlerMode(null);
        }}
        onConfirm={(value) => {
          const codes = value.split("@@").filter(Boolean);
          if (!codes.length) {
            toast.error("请选择至少一个办理人");
            return;
          }
          if ((handlerMode === "transfer" || handlerMode === "depute") && codes.length > 1) {
            toast.error("转办 / 委派只能选择一人");
            return;
          }
          handlerMutation.mutate({ mode: handlerMode, codes });
        }}
      />
    </>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="truncate text-right text-foreground">{value}</dd>
    </div>
  );
}
