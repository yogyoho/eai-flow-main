"use client";

import { Check, MessageSquare, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { type ProjectChapter, type ReportProject } from "@/extensions/project/types";

interface ApprovalStep {
  label: string;
  assignee: string;
  status: "completed" | "in_progress" | "pending";
}

function flattenChapters(chapters: ProjectChapter[]): ProjectChapter[] {
  const result: ProjectChapter[] = [];
  const walk = (items: ProjectChapter[]) => {
    for (const c of items) {
      result.push(c);
      if (c.children?.length) walk(c.children);
    }
  };
  walk(chapters);
  return result;
}

function getApprovalSteps(chapter: ProjectChapter): ApprovalStep[] {
  const author = chapter.assignedName ?? "编辑";
  if (chapter.status === "approved" || chapter.status === "signed") {
    return [
      { label: "编辑提交", assignee: author, status: "completed" },
      { label: "审核人审核", assignee: "审核人", status: "completed" },
      { label: "批准人审批", assignee: "批准人", status: "completed" },
      { label: "定稿完成", assignee: "", status: "completed" },
    ];
  }
  if (chapter.status === "pending_review") {
    return [
      { label: "编辑提交", assignee: author, status: "completed" },
      { label: "审核人审核", assignee: "审核人", status: "in_progress" },
      { label: "批准人审批", assignee: "批准人", status: "pending" },
      { label: "定稿完成", assignee: "", status: "pending" },
    ];
  }
  if (chapter.status === "rejected") {
    return [
      { label: "编辑提交", assignee: author, status: "completed" },
      { label: "审核人审核", assignee: "审核人", status: "completed" },
      { label: "退回修改", assignee: "审核人", status: "completed" },
      { label: "等待重新提交", assignee: "", status: "pending" },
    ];
  }
  return [
    { label: "编辑提交", assignee: author, status: "pending" },
    { label: "审核人审核", assignee: "审核人", status: "pending" },
    { label: "批准人审批", assignee: "批准人", status: "pending" },
    { label: "定稿完成", assignee: "", status: "pending" },
  ];
}

function StepIndicator({ step }: { step: ApprovalStep }) {
  if (step.status === "completed") {
    return (
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-success text-white">
        <Check className="h-3.5 w-3.5" />
      </div>
    );
  }
  if (step.status === "in_progress") {
    return (
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary">
        <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
      </div>
    );
  }
  return <div className="h-7 w-7 shrink-0 rounded-full border border-border" />;
}

const REVIEW_STATUSES = new Set(["pending_review", "rejected", "approved", "signed"]);

interface ApprovalWorkflowProps {
  project: ReportProject;
  onRefresh: () => void;
}

export function ApprovalWorkflow({ project, onRefresh }: ApprovalWorkflowProps) {
  const allChapters = useMemo(() => flattenChapters(project.chapters ?? []), [project.chapters]);
  const reviewChapters = useMemo(() => allChapters.filter((c) => REVIEW_STATUSES.has(c.status)), [allChapters]);
  const [selectedId, setSelectedId] = useState<string | null>(reviewChapters[0]?.id ?? null);
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(false);

  const selectedChapter = allChapters.find((c) => c.id === selectedId);
  const steps = selectedChapter ? getApprovalSteps(selectedChapter) : [];

  const handleApprove = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try { toast.success("已通过审核"); onRefresh(); } catch { toast.error("操作失败"); } finally { setLoading(false); }
  }, [selectedId, onRefresh]);

  const handleReject = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    try { toast.success("已退回修改"); onRefresh(); } catch { toast.error("操作失败"); } finally { setLoading(false); }
  }, [selectedId, onRefresh]);

  return (
    <div className="flex h-full">
      {/* Left panel: approval flow */}
      <div className="flex-1 overflow-y-auto">
        {/* Chapter selector pills */}
        {reviewChapters.length > 0 && (
          <div className="border-b border-border bg-bg px-5 py-3">
            <div className="flex items-center gap-2 overflow-x-auto">
              {reviewChapters.map((ch) => (
                <button
                  key={ch.id}
                  onClick={() => setSelectedId(ch.id)}
                  className={`shrink-0 rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors ${
                    ch.id === selectedId ? "bg-primary text-white" : "bg-[#F1F5F9] text-[#475569] hover:bg-[#E2E8F0]"
                  }`}
                >
                  {ch.title}
                </button>
              ))}
            </div>
          </div>
        )}

        {selectedChapter ? (
          <div className="space-y-5 p-6">
            {/* Chapter info */}
            <div className="rounded-[8px] border border-[#E2E8F0] bg-white p-4 flex flex-col gap-2">
              <h3 className="text-[16px] font-semibold text-foreground">{selectedChapter.title}</h3>
              <div className="flex items-center gap-4 text-[12px] text-[#64748B]">
                {selectedChapter.assignedName && <span>撰写：{selectedChapter.assignedName}</span>}
                <span>{selectedChapter.wordCountCurrent.toLocaleString()}字</span>
                {selectedChapter.updatedAt && (
                  <span>提交于 {new Date(selectedChapter.updatedAt).toLocaleString("zh-CN")}</span>
                )}
              </div>
            </div>

            <h4 className="text-[14px] font-semibold text-foreground">审批流程</h4>

            {/* Vertical step chain */}
            <div className="flex flex-col">
              {steps.map((step, idx) => (
                <div key={idx} className="flex">
                  <div className="flex flex-col items-center mr-3">
                    <StepIndicator step={step} />
                    {idx < steps.length - 1 && (
                      <div className={`w-px flex-1 min-h-[24px] ${step.status === "completed" ? "bg-success" : "bg-[#E2E8F0]"}`} />
                    )}
                  </div>
                  <div className="pb-6 flex-1">
                    <p className={`text-[13px] font-medium ${step.status === "pending" ? "text-[#94A3B8]" : "text-foreground"}`}>
                      {step.label}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2 text-[12px]">
                      {step.assignee && <span className="text-[#64748B]">{step.assignee}</span>}
                      {step.status === "in_progress" && <span className="text-primary">进行中</span>}
                      {step.status === "pending" && <span className="text-[#94A3B8]">待处理</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Action buttons for pending_review */}
            {selectedChapter.status === "pending_review" && (
              <div className="flex items-center gap-2.5 pt-1">
                <Button size="sm" className="bg-success hover:bg-success/90 text-white" onClick={handleApprove} disabled={loading}>
                  <Check className="mr-1.5 h-3.5 w-3.5" /> 通过
                </Button>
                <Button size="sm" variant="outline" className="border-destructive text-destructive hover:bg-destructive/10" onClick={handleReject} disabled={loading}>
                  <X className="mr-1.5 h-3.5 w-3.5" /> 退回修改
                </Button>
                <Button size="sm" variant="outline" onClick={() => {}}>
                  <MessageSquare className="mr-1.5 h-3.5 w-3.5" /> 添加评论
                </Button>
              </div>
            )}

            {/* Comment textarea */}
            <div className="rounded-[8px] border border-[#E2E8F0] bg-white p-3 flex flex-col gap-2">
              <p className="text-[12px] text-[#64748B]">审核意见（可选）</p>
              <Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="输入审核意见..." className="min-h-[80px] resize-none text-sm" />
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-[#94A3B8]">暂无待审批章节</div>
        )}
      </div>

      {/* Right panel: chapter content preview */}
      <div className="w-[360px] shrink-0 overflow-y-auto border-l border-[#E2E8F0] bg-white p-5 flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <h4 className="text-[14px] font-semibold text-foreground">章节内容预览</h4>
          <span className="ml-auto text-[12px] text-[#64748B]">
            {selectedChapter?.wordCountCurrent.toLocaleString() ?? 0} / {selectedChapter?.wordCountTarget.toLocaleString() ?? 0} 字
          </span>
        </div>
        {selectedChapter?.content ? (
          <div className="prose prose-sm max-w-none text-[#64748B]">
            {selectedChapter.content.split("\n").map((p, i) => (
              <p key={i} className="leading-relaxed">{p}</p>
            ))}
          </div>
        ) : (
          <p className="text-[13px] text-[#94A3B8]">暂无内容</p>
        )}
      </div>
    </div>
  );
}
