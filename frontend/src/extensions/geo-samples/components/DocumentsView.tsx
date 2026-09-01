"use client";

// EAI-CUSTOM: geo-sample-bank Phase 1 DocumentsView — bid-quote 原语体系
// (StatCard 统计头 / SectionCard 容器 / FilterBar 筛选条 / ui table),
// 信息架构与计划一致:report_id/文件/阶段/矿种/状态/脱敏摘要/操作 + 上传表单 + 动作按钮。
import { FileStack, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import {
  AMBER,
  BLUE,
  GREEN,
  INK,
  INK_2,
  INK_3,
  PAGE_BG,
  RED,
} from "@/extensions/geo-samples/components/chartTheme";
import {
  FilterBar,
  MINERAL_OPTIONS,
  STAGE_OPTIONS,
  STATUS_OPTIONS,
  type GsbDocFilters,
} from "@/extensions/geo-samples/components/FilterBar";
import { SectionCard } from "@/extensions/geo-samples/components/SectionCard";
import { StatCard } from "@/extensions/geo-samples/components/StatCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/geo-samples/components/ui/table";
import {
  useGsbAction,
  useGsbDocuments,
  useGsbUpload,
} from "@/extensions/geo-samples/hooks";

// 未知状态兜底(Phase 2 后端先行加 compiled 等新值时):显示原文字符 + 中性灰,行不空白不崩溃
const STATUS_LABEL: Record<string, string> = Object.fromEntries(
  STATUS_OPTIONS.map((o) => [o.value, o.label]),
);
const STATUS_COLOR: Record<string, string> = {
  uploaded: INK_2,
  parsed: BLUE,
  redacted: AMBER,
  reviewed: GREEN,
  failed: RED,
};
const STAGE_LABEL: Record<string, string> = Object.fromEntries(
  STAGE_OPTIONS.map((o) => [o.value, o.label]),
);
const MINERAL_LABEL: Record<string, string> = Object.fromEntries(
  MINERAL_OPTIONS.map((o) => [o.value, o.label]),
);

const ACT_BTN =
  "border-border text-foreground hover:border-foreground/40 cursor-pointer rounded border px-2 py-0.5 text-xs transition-colors";

export function DocumentsView() {
  const router = useRouter();
  const [filters, setFilters] = useState<GsbDocFilters>({
    stage: "",
    mineral: "",
    status: "",
  });
  // 统计头走全量(不随筛选联动);列表走筛选
  const allQ = useGsbDocuments({});
  const { data, isLoading } = useGsbDocuments({
    stage: filters.stage || undefined,
    mineral: filters.mineral || undefined,
    status: filters.status || undefined,
  });
  const upload = useGsbUpload();
  const action = useGsbAction();
  const fileRef = useRef<HTMLInputElement>(null);
  const reportIdRef = useRef<HTMLInputElement>(null);

  function onUpload() {
    const file = fileRef.current?.files?.[0];
    const reportId = reportIdRef.current?.value.trim();
    if (!file || !reportId) {
      alert("请填写 report_id（小写字母-数字）并选择 .docx/.pdf 文件");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("report_id", reportId);
    if (filters.stage) fd.append("stage", filters.stage);
    if (filters.mineral) fd.append("mineral", filters.mineral);
    upload.mutate(fd, {
      onSuccess: () => {
        if (fileRef.current) fileRef.current.value = "";
        if (reportIdRef.current) reportIdRef.current.value = "";
      },
      onError: (e) => alert(`上传失败: ${String(e)}`),
    });
  }

  const all = allQ.data?.items ?? [];
  const countBy = (s: string) => all.filter((d) => d.status === s).length;
  const docs = data?.items ?? [];

  return (
    <div
      className="space-y-6 p-6"
      style={{ background: PAGE_BG, minHeight: "100%" }}
    >
      {/* 页头 */}
      <div className="flex items-center gap-3">
        <FileStack className="h-5 w-5" style={{ color: BLUE }} />
        <h1 className="text-[22px] font-bold" style={{ color: INK }}>
          样例文档库
        </h1>
      </div>

      {/* 各状态计数(全量) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        {STATUS_OPTIONS.map((o) => (
          <StatCard
            key={o.value}
            label={o.label}
            value={countBy(o.value)}
            delta={o.value === "uploaded" ? `共 ${all.length} 份` : undefined}
          />
        ))}
      </div>

      {/* ① 上传新样例 */}
      <SectionCard
        badge="①"
        title="上传新样例"
        sub="仅 .docx/.pdf；report_id 全库唯一，相同内容按哈希去重（409 拒绝）"
      >
        <div className="border-border bg-card flex flex-wrap items-center gap-3 rounded-xl border p-4">
          <input
            ref={reportIdRef}
            placeholder="report_id（如 2019-qianxi-gold-expl）"
            className="border-border bg-background placeholder:text-muted-foreground/60 focus:border-foreground/40 w-72 rounded-md border px-2.5 py-1.5 font-mono text-[13px] outline-none"
          />
          <input
            ref={fileRef}
            type="file"
            accept=".docx,.pdf"
            className="text-foreground text-sm"
          />
          <button
            type="button"
            onClick={onUpload}
            disabled={upload.isPending}
            className="flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-1.5 text-[14px] font-medium text-white disabled:cursor-default disabled:opacity-50"
            style={{ background: BLUE }}
          >
            <Upload className="h-4 w-4" />
            {upload.isPending ? "上传中…" : "上传"}
          </button>
          <span className="text-[12px]" style={{ color: INK_3 }}>
            阶段/矿种取下方筛选条当前值（不选则用后端默认：勘探/铜）
          </span>
        </div>
      </SectionCard>

      {/* ② 样例文档列表 */}
      <SectionCard
        badge="②"
        title="样例文档列表"
        sub="解析 → 脱敏 → 抽审 状态流转，5 秒自动刷新"
      >
        <FilterBar filters={filters} onChange={setFilters} />
        <div className="border-border bg-card rounded-xl border p-4">
          {isLoading ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              加载中…
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>report_id</TableHead>
                  <TableHead>文件</TableHead>
                  <TableHead>阶段</TableHead>
                  <TableHead>矿种</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>脱敏摘要</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {docs.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="font-mono text-xs">
                      {d.report_id}
                    </TableCell>
                    <TableCell className="text-[13px]">{d.file_name}</TableCell>
                    <TableCell className="text-[13px]">
                      {STAGE_LABEL[d.stage] ?? d.stage}
                    </TableCell>
                    <TableCell className="text-[13px]">
                      {MINERAL_LABEL[d.mineral] ?? d.mineral}
                    </TableCell>
                    <TableCell>
                      <span
                        className="text-[13px] font-medium"
                        style={{ color: STATUS_COLOR[d.status] ?? INK_2 }}
                      >
                        {STATUS_LABEL[d.status] ?? d.status}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-48 truncate text-xs">
                      {d.redaction_summary ?? "—"}
                    </TableCell>
                    <TableCell>
                      <span className="space-x-1 whitespace-nowrap">
                        {d.status === "uploaded" && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            onClick={() =>
                              action.mutate({ id: d.id, action: "parse" })
                            }
                          >
                            解析
                          </button>
                        )}
                        {d.status === "parsed" && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            onClick={() =>
                              action.mutate({ id: d.id, action: "redact" })
                            }
                          >
                            脱敏
                          </button>
                        )}
                        {d.status === "redacted" && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            onClick={() => router.push("/geo-samples/review")}
                          >
                            抽审
                          </button>
                        )}
                        {d.status === "failed" && (
                          <button
                            type="button"
                            className={ACT_BTN}
                            style={{ color: RED }}
                            onClick={() =>
                              action.mutate({ id: d.id, action: "parse" })
                            }
                          >
                            重试
                          </button>
                        )}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
                {docs.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="text-muted-foreground py-6 text-center text-sm"
                    >
                      暂无样例
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
