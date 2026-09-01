"use client";

// EAI-CUSTOM: geo-sample-bank Phase 1 TasksView — bid-quote 原语体系(SectionCard/ui table),
// 状态配色用 chartTheme 语义色(运行中琥珀/完成绿/失败红),未知值兜底中性灰 + 原文。
import { History } from "lucide-react";

import {
  AMBER,
  BLUE,
  GREEN,
  INK,
  INK_2,
  PAGE_BG,
  RED,
} from "@/extensions/geo-samples/components/chartTheme";
import { SectionCard } from "@/extensions/geo-samples/components/SectionCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/geo-samples/components/ui/table";
import { useGsbRuns } from "@/extensions/geo-samples/hooks";

const RUN_TYPE_ZH: Record<string, string> = {
  parse: "解析",
  redact: "脱敏",
};
const RUN_STATUS_ZH: Record<string, string> = {
  running: "运行中",
  done: "完成",
  failed: "失败",
};
const RUN_STATUS_COLOR: Record<string, string> = {
  running: AMBER,
  done: GREEN,
  failed: RED,
};

export function TasksView() {
  const { data, isPending } = useGsbRuns();
  const runs = data?.items ?? [];
  return (
    <div
      className="space-y-6 p-6"
      style={{ background: PAGE_BG, minHeight: "100%" }}
    >
      {/* 页头 */}
      <div className="flex items-center gap-3">
        <History className="h-5 w-5" style={{ color: BLUE }} />
        <h1 className="text-[22px] font-bold" style={{ color: INK }}>
          运行记录
        </h1>
      </div>

      <SectionCard
        badge="①"
        title="解析 / 脱敏运行记录"
        sub="后台任务执行轨迹，5 秒自动刷新"
      >
        <div className="border-border bg-card rounded-xl border p-4">
          {isPending ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              加载中…
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>类型</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>文档</TableHead>
                  <TableHead>详情</TableHead>
                  <TableHead>时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="text-[13px]">
                      {RUN_TYPE_ZH[r.run_type] ?? r.run_type}
                    </TableCell>
                    <TableCell>
                      <span
                        className="text-[13px] font-medium"
                        style={{ color: RUN_STATUS_COLOR[r.status] ?? INK_2 }}
                      >
                        {RUN_STATUS_ZH[r.status] ?? r.status}
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {r.document_id?.slice(0, 8) ?? "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-72 truncate text-xs">
                      {r.detail ?? "—"}
                    </TableCell>
                    <TableCell className="text-[13px] whitespace-nowrap">
                      {new Date(r.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
                {runs.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="text-muted-foreground py-6 text-center text-sm"
                    >
                      暂无运行
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
