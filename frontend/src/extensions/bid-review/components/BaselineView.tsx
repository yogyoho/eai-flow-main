"use client";

/**
 * 基准确认页(bid:page:baseline)——Task 17 Step 2。
 * 视觉规范:docs/designs/2026-10-29-bid-review-ui-spec.md §3.3(PageHeader + 进度 +
 * 密集表格 + 页顶 warning NoteBar + sticky 确认按钮);确认 = POST /confirm 全量翻转,
 * 后端无行级确认 API,故无逐行 checkbox(spec §3.3 全选=批量确认由全量按钮承担)。
 *
 * landed 后端契约缺口(v1 已记,诚实呈现):
 * - 基线字段快照无 HTTP 读端点(仅 MCP bid_review_baseline_get 有)→ 字段级核对表
 *   待 GET /tasks/{id}/baselines 落地后接入,本页先呈现材料行(engine_meta.docs);
 * - 行级 confirmed 明细同缺口 → 进度按确认门状态位(awaiting_confirm=0%,过门=100%)。
 */

import Link from "next/link";
import { useEffect } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/extensions/bid-review/api";
import { taskStatusPill } from "@/extensions/bid-review/components/primitives";
import { useBidConfirmTask, useBidTask } from "@/extensions/bid-review/hooks";
import { PageHeader } from "@/extensions/contract-price/components/PageHeader";
import { Pill } from "@/extensions/contract-price/components/ui/bits";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/contract-price/components/ui/table";

interface DocMeta {
  doc_id?: string;
  role?: string;
}

function roleLabel(role: string | undefined): string {
  if (role === "tender") return "招标";
  if (role === "bid") return "投标";
  return role ?? "未知";
}

export function BaselineView({ taskId }: { taskId?: string | null }) {
  const taskQuery = useBidTask(taskId ?? null);
  const confirm = useBidConfirmTask();

  const task = taskQuery.data ?? null;
  const gateOpen = task?.status === "awaiting_confirm";
  // 材料行来自 engine_meta.docs(任务详情随带;逐行 payload 的字段快照无读端点)
  const docs = Array.isArray(task?.engine_meta?.docs)
    ? (task.engine_meta.docs as DocMeta[])
    : [];

  useEffect(() => {
    if (confirm.isError) {
      const err = confirm.error;
      // 确认门 409 → toast「存在未复核致命项」(spec §3.2/§3.3;Task 15 收紧落地即生效)
      toast.error(
        err instanceof ApiError && err.status === 409
          ? "存在未复核致命项"
          : (err?.message ?? "确认失败"),
      );
    }
  }, [confirm.isError, confirm.error]);

  if (!taskId) {
    return (
      <div className="flex min-h-0 flex-1 flex-col space-y-4 p-6">
        <PageHeader
          title="基准确认"
          description="逐条核对基准后再确认——基准错误将批量产生错误结论"
        />
        <div className="border-border flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed py-16">
          <p className="text-muted-foreground text-sm">
            未指定任务——请从任务列表进入
          </p>
          <Button size="sm" variant="outline" asChild>
            <Link href="/bid-review">返回任务列表</Link>
          </Button>
        </div>
      </div>
    );
  }

  const st = task ? taskStatusPill(task.status) : null;
  // 进度按确认门状态位(行级 confirmed 明细无读端点,v1 已记缺口)
  const gatePct = gateOpen ? 0 : task ? 100 : 0;
  // materials_hash 安全取串(no-base-to-string):engine_meta 为 Record<unknown>
  const rawHash = task?.engine_meta?.materials_hash;
  const materialsHash = typeof rawHash === "string" ? rawHash : "";

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-4 p-6">
      <div className="shrink-0">
        <PageHeader
          title="基准确认"
          description={`任务 ${taskId.slice(0, 8)} · 基准确认门仅工作台 UI,agent 不可代确认`}
          actions={
            <Button
              variant="outline"
              size="sm"
              onClick={() => void taskQuery.refetch()}
              disabled={taskQuery.isFetching}
            >
              刷新
            </Button>
          }
        />
      </div>

      {/* 页顶 NoteBar(warning 深字):逐条核对后再确认(§3.3) */}
      <div className="flex items-start gap-2 rounded-md border border-[var(--warning-100)] bg-[var(--warning-50)] px-3 py-2 text-xs text-[var(--warning-700)]">
        <span className="flex-1">
          基准错误将批量产生错误结论——逐条核对后再确认。
        </span>
        {st ? <Pill tone={st.tone}>{st.label}</Pill> : null}
      </div>

      {/* 进度(已确认 n/总 m 的 landed 替代:确认门状态位 + 材料份数) */}
      <div className="border-border bg-card flex items-center gap-3 rounded-lg border px-4 py-3">
        <span className="text-muted-foreground text-xs">确认门进度</span>
        <div className="bg-muted h-1.5 w-48 rounded-full">
          <div
            className="bg-primary h-full rounded-full"
            style={{ width: `${gatePct}%` }}
          />
        </div>
        <span className="text-muted-foreground text-xs tabular-nums">
          {gateOpen ? "0%(待确认)" : task ? "100%(已过确认门)" : "—"}
        </span>
        <span className="text-muted-foreground ml-auto text-xs">
          材料 {docs.length} 份 · materials_hash{" "}
          <span className="font-mono">{materialsHash.slice(0, 12) || "—"}</span>
        </span>
      </div>

      {taskQuery.isError ? (
        <div className="bg-destructive/10 text-destructive flex items-center gap-2 rounded-md px-3 py-2 text-xs">
          <span className="flex-1">任务加载失败:{taskQuery.error.message}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void taskQuery.refetch()}
          >
            重试
          </Button>
        </div>
      ) : null}

      {/* 材料行密集表格(field/value/来源锚点列的 landed 替代:字段快照无 HTTP 读端点) */}
      <div className="border-border bg-card overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              {["材料(doc_id)", "角色", "快照哈希", "状态"].map((h) => (
                <TableHead key={h} scope="col">
                  {h}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {taskQuery.isPending ? (
              [0, 1].map((i) => (
                <TableRow key={i}>
                  <TableCell colSpan={4}>
                    <div className="bg-muted h-6 animate-pulse rounded" />
                  </TableCell>
                </TableRow>
              ))
            ) : docs.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={4}
                  className="text-muted-foreground py-8 text-center text-sm"
                >
                  {task ? "该任务无基线材料(任务未生成基线)" : "任务加载中…"}
                </TableCell>
              </TableRow>
            ) : (
              docs.map((d, idx) => (
                <TableRow key={`${d.doc_id ?? "doc"}-${idx}`}>
                  <TableCell>
                    <span className="font-mono text-xs" title={d.doc_id}>
                      {d.doc_id ?? "—"}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Pill tone="gray">{roleLabel(d.role)}</Pill>
                  </TableCell>
                  <TableCell>
                    <span className="text-muted-foreground font-mono text-xs">
                      {materialsHash.slice(0, 12) || "—"}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Pill tone={gateOpen ? "warn" : "success"}>
                      {gateOpen ? "待确认" : "已过确认门"}
                    </Pill>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        <div className="text-muted-foreground flex items-center gap-2 px-4 py-2 text-xs">
          字段级快照核对表待后端补 GET /tasks/&#123;id&#125;/baselines
          读端点后接入(v1 仅 MCP bid_review_baseline_get 可读)。
        </div>
      </div>

      {/* 确认按钮置底 sticky(§3.3);点击触发后端 409 收紧逻辑 */}
      <div className="border-border bg-card sticky bottom-0 flex items-center gap-3 rounded-lg border px-4 py-3">
        <Button
          size="sm"
          disabled={!gateOpen || confirm.isPending}
          onClick={() =>
            confirm.mutate(taskId, {
              onSuccess: () => toast.success("基线已确认,审查续跑中"),
            })
          }
        >
          {confirm.isPending ? "确认中…" : "确认基线并继续审查"}
        </Button>
        <span className="text-muted-foreground text-xs">
          {gateOpen
            ? "确认后任务续跑(running→审查完成)"
            : "当前状态无待确认基线(仅 awaiting_confirm 状态可确认)"}
        </span>
      </div>
    </div>
  );
}
