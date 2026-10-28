"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Ban,
  CircleDashed,
  Clock3,
  FileText,
  GitBranch,
  History,
  Loader2,
  MessageSquare,
  RotateCcw,
  TriangleAlert,
  UserCheck,
  Users,
  Workflow,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useUserDirectory } from "@/lib/directory";
import type { FormSchema, HisTask, InstanceWire, Task } from "@/lib/types";
import { findFormByPath, formValuesFromVariables, parseFormSchema } from "@/lib/forms";
import { PageBody } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { FlowChart } from "@/components/workflow/flow-chart";
import { FormRenderer } from "@/components/workflow/form-renderer";
import { ApprovalDialog } from "@/components/workflow/approval-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn, formatDate, relativeTime } from "@/lib/utils";

const CLOSED_STATUS = ["4", "5", "6", "8"];
const MANAGER_ROLES = ["manager", "director", "admin", "finance"];

export default function InstanceDetailPage() {
  const params = useParams<{ id: string }>();
  const instanceId = Number(params?.id);
  const valid = Number.isFinite(instanceId) && instanceId > 0;
  const queryClient = useQueryClient();
  const { user } = useSession();
  const directory = useUserDirectory();
  const [approvalTask, setApprovalTask] = useState<number | null>(null);
  const [action, setAction] = useState<"revoke" | "terminate" | null>(null);

  const detailQuery = useQuery({
    queryKey: ["instance", instanceId],
    queryFn: () => api.instances.get(instanceId),
    enabled: valid,
    refetchInterval: 30_000,
  });

  const formsQuery = useQuery({
    queryKey: ["forms", "published"],
    queryFn: api.designer.publishedForms,
    staleTime: 60_000,
  });

  const detail = detailQuery.data;
  const instance = detail?.instance;
  const chart = detail?.chart;

  const formPath = useMemo(() => {
    if (!chart) return null;
    const start = (chart.nodeList || []).find((node) => node.nodeType === 0);
    return chart.formPath || start?.formPath || null;
  }, [chart]);

  const boundForm = useMemo(
    () => findFormByPath(formsQuery.data, formPath),
    [formsQuery.data, formPath],
  );

  const schema = useMemo<FormSchema | null>(() => {
    if (!boundForm?.form_content) return null;
    const parsed = parseFormSchema(boundForm.form_content);
    return parsed.fields.length ? parsed : null;
  }, [boundForm]);

  const values = useMemo(
    () => formValuesFromVariables(instance?.variable),
    [instance?.variable],
  );

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["instance", instanceId] });
    queryClient.invalidateQueries({ queryKey: ["instances"] });
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["history"] });
    queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
  }

  if (!valid) {
    return (
      <PageBody>
        <EmptyState
          title="无效的实例 ID"
          description="请从流程实例列表进入详情页。"
          action={
            <Button asChild size="sm" variant="secondary">
              <Link href="/instances">返回实例列表</Link>
            </Button>
          }
        />
      </PageBody>
    );
  }

  if (detailQuery.isLoading) {
    return (
      <PageBody>
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-28 w-full rounded-xl" />
        <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
          <Skeleton className="h-[520px] w-full rounded-xl" />
          <div className="space-y-4">
            <Skeleton className="h-40 w-full rounded-xl" />
            <Skeleton className="h-56 w-full rounded-xl" />
          </div>
        </div>
      </PageBody>
    );
  }

  if (detailQuery.isError || !instance) {
    return (
      <PageBody>
        <EmptyState
          title="实例加载失败"
          description={
            detailQuery.error instanceof ApiError
              ? detailQuery.error.message
              : "请确认工作流后端已启动，然后重试。"
          }
          action={
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => detailQuery.refetch()}>
                重试
              </Button>
              <Button asChild size="sm" variant="ghost">
                <Link href="/instances">返回列表</Link>
              </Button>
            </div>
          }
        />
      </PageBody>
    );
  }

  const active = !CLOSED_STATUS.includes(instance.flow_status);
  const isCreator = instance.create_by === user.handler;
  const isManager = (user.roles || []).some((role) => MANAGER_ROLES.includes(role));
  const canRevoke = active && isCreator;
  const canTerminate = active && (isCreator || isManager);
  const pendingTasks = detail?.tasks || [];

  return (
    <div className="app-grid-bg min-h-screen">
      <PageBody>
        <Link
          href="/instances"
          className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground transition hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          返回流程实例
        </Link>

        <div className="mt-4 overflow-hidden rounded-xl border border-border bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
          <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start">
            <span
              className={cn(
                "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border",
                active
                  ? "border-amber-100 bg-amber-50 text-amber-600"
                  : "border-emerald-100 bg-emerald-50 text-emerald-600",
              )}
            >
              {active ? <CircleDashed className="h-5 w-5" /> : <GitBranch className="h-5 w-5" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.015em]">
                  {instance.flow_name || "流程实例"}
                </h1>
                <StatusBadge
                  tone={instance.flow_status_tone}
                  label={instance.flow_status_label || instance.flow_status}
                />
                <Badge variant="outline" className="font-mono text-[10px]">
                  #{instance.id}
                </Badge>
              </div>
              <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[11.5px] text-muted-foreground">
                <span className="font-mono">{instance.business_id || `INSTANCE-${instance.id}`}</span>
                <span className="text-border">/</span>
                <span>当前节点 {instance.node_name || instance.node_code || "—"}</span>
                <span className="text-border">/</span>
                <span>更新于 {relativeTime(instance.update_time || instance.create_time)}</span>
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {canRevoke && (
                <Button variant="secondary" size="sm" onClick={() => setAction("revoke")}>
                  <RotateCcw className="h-3.5 w-3.5" />
                  撤销
                </Button>
              )}
              {canTerminate && (
                <Button
                  variant="outline"
                  size="sm"
                  className="border-rose-200 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                  onClick={() => setAction("terminate")}
                >
                  <Ban className="h-3.5 w-3.5" />
                  终止
                </Button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-4 gap-y-4 border-t border-border px-5 py-4 lg:grid-cols-4">
            <Meta
              icon={UserCheck}
              label="发起人"
              value={directory.name(instance.create_by)}
              hint={instance.create_by}
            />
            <Meta
              icon={Clock3}
              label="发起时间"
              value={formatDate(instance.create_time)}
              hint={relativeTime(instance.create_time)}
            />
            <Meta
              icon={Workflow}
              label="当前节点"
              value={instance.node_name || "—"}
              hint={instance.node_code || "—"}
            />
            <Meta
              icon={Users}
              label="待办任务"
              value={pendingTasks.length ? `${pendingTasks.length} 个节点待处理` : "无"}
              hint={active ? "流程运行中" : "流程已结束"}
            />
          </div>
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-5">
            <FlowChart chart={chart!} />

            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <div className="flex items-center gap-2 border-b border-border px-4 py-3">
                <History className="h-4 w-4 text-muted-foreground" />
                <p className="text-[12.5px] font-semibold">审批时间线</p>
                <span className="text-[10.5px] text-muted-foreground">
                  共 {(detail?.history || []).length} 条记录
                </span>
              </div>
              {(detail?.history || []).length ? (
                <div className="p-5">
                  <div className="relative space-y-5 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-border">
                    {[...(detail?.history || [])]
                      .sort((a, b) => {
                        const at = new Date(a.create_time || 0).getTime();
                        const bt = new Date(b.create_time || 0).getTime();
                        return at === bt ? a.id - b.id : at - bt;
                      })
                      .map((his) => (
                        <TimelineItem
                          key={his.id}
                          his={his}
                          approver={directory.name(his.approver)}
                        />
                      ))}
                  </div>
                </div>
              ) : (
                <div className="p-4">
                  <EmptyState
                    title="暂无审批记录"
                    description="流程刚发起时可能还没有产生历史任务。"
                    className="border-0 bg-transparent py-10"
                  />
                </div>
              )}
            </div>
          </div>

          <aside className="space-y-4">
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <div className="flex items-center gap-2 border-b border-border px-4 py-3">
                <MessageSquare className="h-4 w-4 text-muted-foreground" />
                <p className="text-[12.5px] font-semibold">待办任务</p>
                {pendingTasks.length > 0 && (
                  <Badge variant="warning" className="ml-auto">
                    {pendingTasks.length}
                  </Badge>
                )}
              </div>
              {pendingTasks.length ? (
                <div className="divide-y divide-border">
                  {pendingTasks.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      currentUser={user.handler}
                      directoryName={directory.name}
                      onApprove={() => setApprovalTask(task.id)}
                    />
                  ))}
                </div>
              ) : (
                <p className="px-4 py-6 text-center text-[11.5px] text-muted-foreground">
                  {active ? "当前没有活跃待办" : "流程已结束，无待办任务"}
                </p>
              )}
            </div>

            <div className="overflow-hidden rounded-xl border border-border bg-card">
              <div className="flex items-center gap-2 border-b border-border px-4 py-3">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <p className="text-[12.5px] font-semibold">表单快照</p>
                {boundForm && (
                  <Badge variant="outline" className="ml-auto">
                    {boundForm.form_name} v{boundForm.version}
                  </Badge>
                )}
              </div>
              <div className="p-4">
                {schema ? (
                  <FormRenderer schema={schema} values={values} readOnly compact />
                ) : Object.keys(values).length ? (
                  <dl className="space-y-2.5">
                    {Object.entries(values).map(([key, value]) => (
                      <div key={key} className="flex items-start justify-between gap-3">
                        <dt className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
                          {key}
                        </dt>
                        <dd className="break-all text-right text-[12px] text-foreground">
                          {formatVariable(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="py-4 text-center text-[11.5px] text-muted-foreground">
                    该实例没有业务变量
                  </p>
                )}
              </div>
              {instance.variable && Object.keys(instance.variable).length > 0 && (
                <details className="border-t border-border bg-muted/20 px-4 py-3">
                  <summary className="cursor-pointer list-none text-[10.5px] font-medium text-muted-foreground [&::-webkit-details-marker]:hidden">
                    查看原始变量 JSON
                  </summary>
                  <pre className="mt-2 max-h-56 overflow-auto rounded-lg border border-border bg-card p-3 text-[10.5px] leading-relaxed text-muted-foreground">
                    {JSON.stringify(instance.variable, null, 2)}
                  </pre>
                </details>
              )}
            </div>

            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                实例信息
              </p>
              <dl className="mt-3 space-y-2.5 text-[11.5px]">
                <InfoRow label="流程定义" value={instance.flow_name || "—"} />
                <InfoRow label="定义 ID" value={String(instance.definition_id)} />
                <InfoRow label="业务编号" value={instance.business_id || "—"} />
                <InfoRow label="发起身份" value={instance.create_by} />
                <InfoRow label="更新时间" value={formatDate(instance.update_time)} />
              </dl>
            </div>
          </aside>
        </div>

        <p className="mt-4 text-[11px] text-muted-foreground/80">
          流程图与历史记录每 30 秒自动刷新；撤销与终止操作会写入历史任务并关闭当前待办。
        </p>
      </PageBody>

      <ApprovalDialog
        open={approvalTask !== null}
        taskId={approvalTask}
        hisId={null}
        onOpenChange={(open) => {
          if (!open) setApprovalTask(null);
        }}
        onDone={refresh}
      />

      <InstanceActionDialog
        action={action}
        instance={instance}
        onOpenChange={(open) => {
          if (!open) setAction(null);
        }}
        onDone={refresh}
      />
    </div>
  );
}

function Meta({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0">
        <p className="text-[10.5px] text-muted-foreground">{label}</p>
        <p className="truncate text-[12.5px] font-medium text-foreground">{value}</p>
        {hint && <p className="truncate text-[10px] text-muted-foreground/80">{hint}</p>}
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="truncate text-right text-foreground">{value}</dd>
    </div>
  );
}

function TaskCard({
  task,
  currentUser,
  directoryName,
  onApprove,
}: {
  task: Task;
  currentUser: string;
  directoryName: (handler?: string | null) => string;
  onApprove: () => void;
}) {
  const assignees = task.assignees || [];
  const canHandle = assignees.length === 0 || assignees.includes(currentUser);
  return (
    <div className="px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[12.5px] font-medium">{task.node_name || task.node_code}</p>
          <p className="mt-0.5 text-[10.5px] text-muted-foreground">
            待办 #{task.id} · {formatDate(task.create_time)}
          </p>
        </div>
        <Badge variant="warning" className="shrink-0">
          待审批
        </Badge>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {assignees.length ? (
          assignees.map((handler) => (
            <Badge key={handler} variant={handler === currentUser ? "default" : "outline"}>
              {directoryName(handler)}
            </Badge>
          ))
        ) : (
          <Badge variant="outline">未指定办理人 · 可认领</Badge>
        )}
      </div>
      {canHandle && (
        <Button size="sm" className="mt-3 h-7 w-full" onClick={onApprove}>
          去审批
        </Button>
      )}
    </div>
  );
}

function TimelineItem({ his, approver }: { his: HisTask; approver: string }) {
  const rejected = his.skip_type === "REJECT" || his.flow_status === "9";
  const finished = ["2", "3", "8"].includes(his.flow_status);
  const terminated = ["4", "5", "6"].includes(his.flow_status);
  const tone = rejected
    ? "border-rose-200 bg-rose-50 text-rose-600"
    : terminated
      ? "border-slate-200 bg-slate-100 text-slate-500"
      : finished
        ? "border-emerald-200 bg-emerald-50 text-emerald-600"
        : "border-amber-200 bg-amber-50 text-amber-600";

  return (
    <div className="relative pl-7">
      <span
        className={cn(
          "absolute left-0 top-0 flex h-3.5 w-3.5 items-center justify-center rounded-full border-2 bg-card",
          tone,
        )}
      >
        <span className="h-1 w-1 rounded-full bg-current" />
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[12.5px] font-medium">{his.node_name || his.node_code || "流程节点"}</p>
        <Badge
          variant={rejected ? "danger" : terminated ? "slate" : finished ? "success" : "warning"}
          className="font-normal"
        >
          {his.flow_status_label || his.cooperate_label || "处理中"}
        </Badge>
        {his.cooperate_label && his.cooperate_type > 1 && (
          <Badge variant="outline">{his.cooperate_label}</Badge>
        )}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {approver}
        {his.collaborator ? ` · 协作 ${his.collaborator}` : ""}
        <span className="mx-1.5 text-border">/</span>
        {formatDate(his.create_time)}
      </p>
      {his.message ? (
        <p className="mt-2 rounded-lg border border-border bg-muted/25 px-3 py-2 text-[11.5px] leading-relaxed text-foreground/90">
          {his.message}
        </p>
      ) : null}
      {his.target_node_name ? (
        <p className="mt-1.5 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
          <GitBranch className="h-3 w-3" />
          流转至 {his.target_node_name}
        </p>
      ) : null}
    </div>
  );
}

function InstanceActionDialog({
  action,
  instance,
  onOpenChange,
  onDone,
}: {
  action: "revoke" | "terminate" | null;
  instance: InstanceWire;
  onOpenChange: (open: boolean) => void;
  onDone: () => void;
}) {
  const [message, setMessage] = useState("");
  const isRevoke = action === "revoke";

  const mutation = useMutation({
    mutationFn: () =>
      isRevoke
        ? api.instances.revoke(instance.id, message)
        : api.instances.terminate(instance.id, message),
    onSuccess: () => {
      toast.success(isRevoke ? "流程已撤销" : "流程已终止");
      onOpenChange(false);
      setMessage("");
      onDone();
    },
    onError: (error: unknown) =>
      toast.error(error instanceof ApiError ? error.message : "操作失败"),
  });

  return (
    <Dialog
      open={action !== null}
      onOpenChange={(open) => {
        if (!open) setMessage("");
        onOpenChange(open);
      }}
    >
      <DialogContent className="max-w-[460px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-lg",
                isRevoke ? "bg-amber-50 text-amber-600" : "bg-rose-50 text-rose-600",
              )}
            >
              {isRevoke ? <RotateCcw className="h-4 w-4" /> : <TriangleAlert className="h-4 w-4" />}
            </span>
            {isRevoke ? "撤销流程" : "终止流程"}
          </DialogTitle>
          <DialogDescription>
            {isRevoke
              ? "撤销后流程回到发起节点，当前待办全部关闭，可由发起人重新提交。"
              : "终止后所有未处理待办将关闭，实例状态标记为已终止，且不可恢复。"}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-1">
          <div className="rounded-lg border border-border bg-muted/25 px-3 py-2 text-[11.5px] text-muted-foreground">
            {instance.flow_name || "流程实例"} ·{" "}
            <span className="font-mono">{instance.business_id || `#${instance.id}`}</span>
          </div>
          <Textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={isRevoke ? "请填写撤销原因…" : "请填写终止原因…"}
            className="min-h-[84px]"
          />
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
            取消
          </Button>
          <Button
            variant={isRevoke ? "default" : "destructive"}
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {isRevoke ? "确认撤销" : "确认终止"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function formatVariable(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
