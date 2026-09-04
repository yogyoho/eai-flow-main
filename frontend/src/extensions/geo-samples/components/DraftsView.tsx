"use client";

// EAI-CUSTOM: P5 T6 人审 tab（plan 2026-09-04-geo-p5-orepack）——ore_pack 草稿清单/
// 逐字段核对/approve-reject。V1 = 列表 + JSON 预览（plan 明确不做 diff 视图）；
// approve 前置 = errors==[]（后端双闸，前端置灰只是引导）；approve 响应携带
// repo 落盘路径 + standards_index 扩容义务清单。风格沿 TasksView/ReviewView 原语体系。
import { Package } from "lucide-react";
import { useState } from "react";

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
import { SectionCard } from "@/extensions/geo-samples/components/SectionCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/extensions/geo-samples/components/ui/table";
import {
  useGsbDraftReview,
  useGsbDrafts,
} from "@/extensions/geo-samples/hooks";
import type {
  GsbOrePackApproveResult,
  GsbOrePackDraft,
} from "@/extensions/geo-samples/types";

const STATUS_ZH: Record<string, string> = {
  draft: "待审",
  approved: "已过审",
  rejected: "已驳回",
};
const STATUS_COLOR: Record<string, string> = {
  draft: AMBER,
  approved: GREEN,
  rejected: RED,
};
const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "全部" },
  { value: "draft", label: "待审" },
  { value: "approved", label: "已过审" },
  { value: "rejected", label: "已驳回" },
];

export function DraftsView() {
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [approval, setApproval] = useState<GsbOrePackApproveResult | null>(
    null,
  );
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isPending } = useGsbDrafts(
    statusFilter ? { review_status: statusFilter } : undefined,
  );
  const drafts = data?.items ?? [];
  const selected: GsbOrePackDraft | null =
    drafts.find((d) => d.id === selectedId) ?? null;
  const review = useGsbDraftReview();

  function selectDraft(d: GsbOrePackDraft) {
    setSelectedId(d.id);
    setNote(d.review_note ?? "");
    setApproval(null);
    setActionError(null);
  }

  function submit(action: "approve" | "reject") {
    if (!selected) return;
    setActionError(null);
    review.mutate(
      { id: selected.id, action, note: note || null },
      {
        onSuccess: (result) => {
          // approve 分支才落 approval（reject 返回 GsbOrePackDraft，联合类型收窄给 TS）
          if (action === "approve")
            setApproval(result as GsbOrePackApproveResult);
          else setApproval(null);
        },
        onError: (e: Error) => setActionError(e.message),
      },
    );
  }

  const approveBlocked =
    selected?.review_status !== "draft" ||
    selected.errors.length > 0 ||
    selected.draft_json == null;

  return (
    <div
      className="space-y-6 p-6"
      style={{ background: PAGE_BG, minHeight: "100%" }}
    >
      {/* 页头 */}
      <div className="flex items-center gap-3">
        <Package className="h-5 w-5" style={{ color: BLUE }} />
        <h1 className="text-[22px] font-bold" style={{ color: INK }}>
          矿种包孵化
        </h1>
      </div>

      <SectionCard
        badge="①"
        title="草稿清单"
        sub="LLM 抽取草稿（后台任务，5 秒自动刷新）；点击行进入逐字段核对"
      >
        <div className="mb-3 flex gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setStatusFilter(f.value)}
              className="cursor-pointer rounded-md border px-2.5 py-1 text-[13px]"
              style={{
                borderColor:
                  statusFilter === f.value ? BLUE : "rgba(0,0,0,0.06)",
                color: statusFilter === f.value ? BLUE : INK_2,
                background: statusFilter === f.value ? "#eef1ff" : undefined,
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="border-border bg-card rounded-xl border p-4">
          {isPending ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              加载中…
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>矿种</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>校验</TableHead>
                  <TableHead>切片指纹</TableHead>
                  <TableHead>创建时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {drafts.map((d) => (
                  <TableRow
                    key={d.id}
                    onClick={() => selectDraft(d)}
                    className="cursor-pointer"
                    style={
                      d.id === selectedId
                        ? { background: "#eef1ff" }
                        : undefined
                    }
                  >
                    <TableCell className="text-[13px] font-medium">
                      {d.mineral}
                    </TableCell>
                    <TableCell>
                      <span
                        className="text-[13px] font-medium"
                        style={{
                          color: STATUS_COLOR[d.review_status] ?? INK_2,
                        }}
                      >
                        {STATUS_ZH[d.review_status] ?? d.review_status}
                      </span>
                    </TableCell>
                    <TableCell>
                      {d.errors.length === 0 ? (
                        <span className="text-[13px]" style={{ color: GREEN }}>
                          通过
                        </span>
                      ) : (
                        <span
                          className="text-[13px]"
                          title={d.errors.join("；")}
                          style={{ color: RED }}
                        >
                          {d.errors.length} 项
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {d.slices_hash.slice(0, 10)}…
                    </TableCell>
                    <TableCell className="text-[13px] whitespace-nowrap">
                      {new Date(d.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
                {drafts.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="text-muted-foreground py-6 text-center text-sm"
                    >
                      暂无草稿（CLI ore-pack extract 触发抽取后自动出现）
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </div>
      </SectionCard>

      <SectionCard
        badge="②"
        title="逐字段核对"
        sub="JSON 预览 + 校验错误 + 审阅意见；过审即落 repo ore_packs/<矿种>.json"
      >
        {selected ? (
          <div className="space-y-3">
            {/* 校验错误区（人审可见，approve 前置 = errors==[]） */}
            {selected.errors.length > 0 && (
              <div
                className="rounded-md p-3 text-[13px]"
                style={{ background: "#fdf1f1", color: RED }}
              >
                <p className="font-medium">
                  校验未过 {selected.errors.length} 项（禁止过审）：
                </p>
                <ul className="mt-1 list-disc pl-5">
                  {selected.errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
            {selected.draft_json == null && (
              <div
                className="rounded-md p-3 text-[13px]"
                style={{ background: "#fdf1f1", color: RED }}
              >
                失败草稿：后端未产出 JSON（见错误信息）
              </div>
            )}
            {/* JSON 预览（逐字段核对 V1 形态） */}
            <pre
              className="border-border bg-card max-h-96 overflow-auto rounded-xl border p-4 text-xs"
              style={{ color: INK }}
            >
              {selected.draft_json == null
                ? "（无 JSON）"
                : JSON.stringify(selected.draft_json, null, 2)}
            </pre>
            {/* approve 结果：落盘路径 + standards_index 义务清单 */}
            {approval && (
              <div
                className="rounded-md p-3 text-[13px]"
                style={{ background: "#eefaf3", color: GREEN }}
              >
                <p className="font-medium">已过审，落盘 {approval.written}</p>
                {approval.standards_index_obligations.length > 0 ? (
                  <>
                    <p className="mt-1" style={{ color: AMBER }}>
                      standards_index 扩容义务（
                      {approval.standards_index_obligations.length}{" "}
                      项【待核实】仍须人工对照规范原文录入）：
                    </p>
                    <ul className="mt-1 list-disc pl-5">
                      {approval.standards_index_obligations.map((o, i) => (
                        <li key={i}>{o}</li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p className="mt-1">无【待核实】义务。</p>
                )}
              </div>
            )}
            {actionError && (
              <p className="text-[13px]" style={{ color: RED }}>
                {actionError}
              </p>
            )}
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="审阅意见（reject 时建议写明理由）"
              className="border-border bg-background placeholder:text-muted-foreground/60 focus:border-foreground/40 w-full rounded-md border p-2 text-[14px] outline-none"
            />
            <div className="flex gap-2">
              <button
                type="button"
                disabled={approveBlocked || review.isPending}
                onClick={() => submit("approve")}
                className="cursor-pointer rounded-md px-3 py-1.5 text-[14px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
                style={{ background: GREEN }}
              >
                过审（落 repo）
              </button>
              <button
                type="button"
                disabled={
                  selected.review_status !== "draft" || review.isPending
                }
                onClick={() => submit("reject")}
                className="cursor-pointer rounded-md px-3 py-1.5 text-[14px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
                style={{ background: RED }}
              >
                驳回
              </button>
              <span className="self-center text-xs" style={{ color: INK_3 }}>
                {selected.review_status !== "draft"
                  ? `该草稿已${STATUS_ZH[selected.review_status] ?? selected.review_status}`
                  : approveBlocked
                    ? "校验未过，不可过审（可驳回）"
                    : ""}
              </span>
            </div>
          </div>
        ) : (
          <p className="text-[13px]" style={{ color: INK_3 }}>
            请先在上方选择草稿
          </p>
        )}
      </SectionCard>
    </div>
  );
}
