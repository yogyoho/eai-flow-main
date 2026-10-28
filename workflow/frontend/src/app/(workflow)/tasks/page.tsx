"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Inbox,
  RefreshCw,
  RotateCcw,
  Workflow,
} from "lucide-react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useUserDirectory } from "@/lib/directory";
import type { HisTask, Task } from "@/lib/types";
import { PageBody, PageHeader } from "@/components/page-header";
import { ApprovalDialog } from "@/components/workflow/approval-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn, formatDate, initials, relativeTime } from "@/lib/utils";

const NODE_COLOR: Record<number, { bg: string; text: string }> = {
  0: { bg: "bg-emerald-50", text: "text-emerald-600" },
  1: { bg: "bg-sky-50", text: "text-sky-600" },
  2: { bg: "bg-rose-50", text: "text-rose-600" },
  3: { bg: "bg-amber-50", text: "text-amber-600" },
  4: { bg: "bg-cyan-50", text: "text-cyan-600" },
  5: { bg: "bg-violet-50", text: "text-violet-600" },
};

export default function TasksPage() {
  const { user } = useSession();
  const directory = useUserDirectory();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("todo");
  const [activeTask, setActiveTask] = useState<number | null>(null);
  const [activeHis, setActiveHis] = useState<number | null>(null);

  const tasksQuery = useQuery({
    queryKey: ["tasks", user.handler],
    queryFn: () => api.tasks.list({ assignee: user.handler, size: 100 }),
    refetchInterval: 30_000,
  });

  const historyQuery = useQuery({
    queryKey: ["history", user.handler],
    queryFn: () => api.tasks.history({ handler: user.handler, size: 100 }),
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
    queryClient.invalidateQueries({ queryKey: ["history"] });
    queryClient.invalidateQueries({ queryKey: ["instances"] });
    queryClient.invalidateQueries({ queryKey: ["meta", "stats"] });
  }

  const tasks = tasksQuery.data?.items || [];
  const history = historyQuery.data?.items || [];

  return (
    <div className="app-grid-bg min-h-screen">
      <PageBody>
        <PageHeader
          eyebrow="My Inbox"
          title="我的待办"
          description="按当前身份汇总待审批任务与已办记录。审批时可直接填写业务表单并选择通过、退回或转办。"
          actions={
            <>
              <Button variant="secondary" onClick={refresh}>
                <RefreshCw className="h-4 w-4" />
                刷新
              </Button>
              <Button asChild>
                <Link href="/instances">
                  发起流程
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              </Button>
            </>
          }
        />

        <div className="mt-6 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-900 text-[11px] font-semibold text-white">
            {initials(user.name)}
          </span>
          <div>
            <p className="text-[13px] font-medium">
              {user.name}
              <span className="ml-2 text-[11px] font-normal text-muted-foreground">
                {user.group} · {user.handler}
              </span>
            </p>
            <p className="text-[11px] text-muted-foreground">
              当前身份办理 · 角色 {(user.roles || []).join(" / ") || "employee"}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-4 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
              待办 {tasks.length}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              已办 {history.length}
            </span>
          </div>
        </div>

        <Tabs value={tab} onValueChange={setTab} className="mt-6">
          <TabsList>
            <TabsTrigger value="todo">
              待办任务
              {tasks.length > 0 && (
                <span className="rounded-full bg-primary/15 px-1.5 text-[10px] font-semibold">
                  {tasks.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="done">已办记录</TabsTrigger>
          </TabsList>

          <div className="mt-4 overflow-hidden rounded-xl border border-border bg-card">
            {tab === "todo" ? (
              tasksQuery.isLoading ? (
                <div className="space-y-3 p-4">
                  {[0, 1, 2].map((index) => (
                    <Skeleton key={index} className="h-20 w-full" />
                  ))}
                </div>
              ) : tasks.length === 0 ? (
                <div className="p-4">
                  <EmptyState
                    title="暂无待办任务"
                    description="当前身份没有需要处理的审批。可以在流程实例页发起一个流程，体验完整流转。"
                    icon={<Inbox className="h-5 w-5" />}
                    action={
                      <Button asChild size="sm" variant="secondary">
                        <Link href="/instances">去发起流程</Link>
                      </Button>
                    }
                  />
                </div>
              ) : (
                <div className="divide-y divide-border">
                  {tasks.map((task) => (
                    <TaskRow
                      key={task.id}
                      task={task}
                      assigneeName={directory.name(user.handler)}
                      onOpen={() => setActiveTask(task.id)}
                    />
                  ))}
                </div>
              )
            ) : historyQuery.isLoading ? (
              <div className="space-y-3 p-4">
                {[0, 1, 2].map((index) => (
                  <Skeleton key={index} className="h-16 w-full" />
                ))}
              </div>
            ) : history.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  title="暂无已办记录"
                  description="处理过的审批会显示在这里，可回看表单快照、审批意见与流转结果。"
                  icon={<Clock3 className="h-5 w-5" />}
                />
              </div>
            ) : (
              <div className="divide-y divide-border">
                {history.map((his) => (
                  <HistoryRow
                    key={his.id}
                    his={his}
                    name={directory.name(his.approver)}
                    onOpen={() => setActiveHis(his.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </Tabs>

        <p className="mt-4 text-[11px] text-muted-foreground/80">
          待办每 30 秒自动刷新；所有审批结果会写入 flow_his_task，并同步更新流程实例进度图。
        </p>
      </PageBody>

      <ApprovalDialog
        open={activeTask !== null || activeHis !== null}
        taskId={activeTask}
        hisId={activeHis}
        onOpenChange={(open) => {
          if (!open) {
            setActiveTask(null);
            setActiveHis(null);
          }
        }}
        onDone={refresh}
      />
    </div>
  );
}

function TaskRow({
  task,
  assigneeName,
  onOpen,
}: {
  task: Task;
  assigneeName: string;
  onOpen: () => void;
}) {
  const color = NODE_COLOR[task.node_type] || NODE_COLOR[1];
  return (
    <div className="group flex flex-col gap-3 p-4 transition hover:bg-primary/[0.025] sm:flex-row sm:items-center">
      <span
        className={cn(
          "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border",
          color.bg,
          color.text,
        )}
      >
        <Workflow className="h-[18px] w-[18px]" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-[13.5px] font-medium">{task.flow_name || "流程任务"}</p>
          <Badge variant="warning" className="gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            {task.node_name || task.node_code}
          </Badge>
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="font-mono">{task.business_id || `INSTANCE-${task.instance_id}`}</span>
          <span className="text-border">/</span>
          <span>待办 #{task.id}</span>
          <span className="text-border">/</span>
          <span>{formatDate(task.create_time)}</span>
        </p>
      </div>
      <div className="flex items-center gap-4">
        <span className="hidden items-center gap-1.5 text-[11px] text-muted-foreground sm:flex">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-[9px] font-medium">
            {initials(assigneeName)}
          </span>
          {assigneeName}
        </span>
        <span className="hidden text-[11px] text-muted-foreground lg:block">
          {relativeTime(task.create_time)}
        </span>
        <Button size="sm" onClick={onOpen}>
          去审批
        </Button>
      </div>
    </div>
  );
}

function HistoryRow({
  his,
  name,
  onOpen,
}: {
  his: HisTask;
  name: string;
  onOpen: () => void;
}) {
  const rejected = his.skip_type === "REJECT" || his.flow_status === "9";
  const pending = his.flow_status === "1" || his.flow_status === "0";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full flex-col gap-3 p-4 text-left transition hover:bg-primary/[0.025] sm:flex-row sm:items-center"
    >
      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border",
          rejected
            ? "border-rose-100 bg-rose-50 text-rose-600"
            : "border-emerald-100 bg-emerald-50 text-emerald-600",
        )}
      >
        {rejected ? <RotateCcw className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-[13px] font-medium">
            {his.flow_name || "流程"} · {his.node_name || his.node_code}
          </p>
          {rejected ? (
            <Badge variant="danger">退回</Badge>
          ) : pending ? (
            <Badge variant="warning">处理中</Badge>
          ) : (
            <Badge variant="success">{his.cooperate_label || "审批通过"}</Badge>
          )}
        </div>
        <p className="mt-1 line-clamp-1 text-[11px] text-muted-foreground">
          {name} · {his.message || "未填写意见"}
          {his.target_node_name ? ` · 流转至 ${his.target_node_name}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3 text-[11px] text-muted-foreground">
        <span>{formatDate(his.create_time)}</span>
        <span className="text-primary opacity-0 transition group-hover:opacity-100">查看</span>
      </div>
    </button>
  );
}
