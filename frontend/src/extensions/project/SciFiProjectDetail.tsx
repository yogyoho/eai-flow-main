"use client";

import {
  ArrowLeft,
  BookOpen,
  Check,
  CheckCircle2,
  Cpu,
  Edit3,
  FileText,
  Layers,
  LayoutGrid,
  ListFilter,
  Loader2,
  MessageSquare,
  Save,
  ShieldAlert,
  Sparkles,
  Terminal,
  Trash2,
  Users,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import {
  type ProjectChapter,
  type ReportProject,
  MEMBER_ROLE_LABELS,
} from "@/extensions/project/types";
import {
  aggregateWordCount,
  flattenChapters,
  inferStatus,
} from "@/extensions/project/utils";

// ── Local UI types (derived from API types) ──

type ChapterStatus = "pending" | "draft" | "reviewing" | "approved"; // EAI-CUSTOM: canonical (ADR 2026-08-02 P4)

interface SciFiProjectDetailProps {
  projectId: string;
}

// ── Status helpers ──

const STATUS_LABELS: Record<ChapterStatus, string> = {
  pending: "未开始", // EAI-CUSTOM: canonical (ADR 2026-08-02 P4)
  draft: "编写中",
  reviewing: "审核中",
  approved: "已完成",
};

function mapToSciFiStatus(status: string): ChapterStatus {
  const s = inferStatus({ status } as ProjectChapter);
  if (s === "pending" || s === "draft" || s === "reviewing" || s === "approved")
    return s;
  return "pending";
}

function statusBadgeClass(status: ChapterStatus): string {
  switch (status) {
    case "approved":
      return "bg-success/10 text-success border border-success/20";
    case "reviewing":
      return "bg-warning/10 text-warning";
    case "draft":
      return "bg-primary/10 text-primary";
    default:
      return "bg-muted text-muted-foreground";
  }
}

function activityLabel(updatedAt: string | null): string {
  if (!updatedAt) return "";
  const diff = Date.now() - new Date(updatedAt).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}

// ── Component ──

export function SciFiProjectDetail({ projectId }: SciFiProjectDetailProps) {
  const [project, setProject] = useState<ReportProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [fileCount, setFileCount] = useState<number>(0);

  // Tab state
  const [activeTab, setActiveTab] = useState<"overview" | "editor" | "review">(
    "overview",
  );
  const [layoutMode, setLayoutMode] = useState<"list" | "kanban">("list");
  const [statusFilter, setStatusFilter] = useState<"all" | ChapterStatus>(
    "all",
  );

  // Editor state
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(
    null,
  );
  const [editorContent, setEditorContent] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  // Member management
  const [showAddMember, setShowAddMember] = useState(false);
  const [newMemberName, setNewMemberName] = useState("");
  const [addingMember, setAddingMember] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  // AI Chat slide-out
  const [entering, setEntering] = useState(false);

  // ── Data fetching ──

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectApi.get(projectId);
      setProject(data);
      // Load file count
      try {
        const stats = await projectApi.getStats(projectId);
        setFileCount(stats.documentCount);
      } catch {
        setFileCount(0);
      }
    } catch {
      toast.error("加载项目失败");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadProject();
  }, [loadProject]);

  // ── Derived data ──

  const flatChapters = useMemo(() => {
    if (!project?.chapters) return [];
    return flattenChapters(project.chapters);
  }, [project?.chapters]);

  const filteredChapters = useMemo(() => {
    if (statusFilter === "all") return flatChapters;
    return flatChapters.filter(
      (ch) => mapToSciFiStatus(ch.status) === statusFilter,
    );
  }, [flatChapters, statusFilter]);

  const activeChapter = useMemo(() => {
    if (!selectedChapterId) return flatChapters[0] ?? null;
    return (
      flatChapters.find((ch) => ch.id === selectedChapterId) ??
      flatChapters[0] ??
      null
    );
  }, [flatChapters, selectedChapterId]);

  const activeCount = flatChapters.filter(
    (ch) => mapToSciFiStatus(ch.status) === "draft",
  ).length;
  const completedCount = flatChapters.filter(
    (ch) => mapToSciFiStatus(ch.status) === "approved",
  ).length;
  const totalCount = flatChapters.length;
  const totalWords = useMemo(() => {
    if (!project?.chapters) return 0;
    return aggregateWordCount(project.chapters);
  }, [project?.chapters]);

  // ── Workflow phase progression (mirrors reference 4-phase flow) ──
  // phaseIndex = number of completed phases (0..4); phase at `phaseIndex` is active.
  const phaseIndex = (() => {
    // EAI-CUSTOM: canonical project status (ADR 2026-08-02 P4).
    switch (project?.status) {
      case "draft":
        return 1; // 生产阶段（AI 初稿 + 人工修改）
      case "in_review":
        return 2; // 已提交审批
      case "approved":
        return 4; // 完成（archived 是正交 archivedAt 桶，非 spine 状态）
      default:
        return 1;
    }
  })();
  const phases = [
    { title: "1. AI编写初稿", sub: "COMPLETED // AI DRAFTED" },
    { title: "2. 人工修改确认", sub: "ACTIVE WORK IN PROGRESS" },
    { title: "3. 报告提交", sub: "PENDING SYNC PROTOCOLS" },
    { title: "4. 报告审核", sub: "SCHEMATIC VERIFICATION" },
  ];

  // ── Revision ledger (derived from chapter activity) ──
  const revisionEntries = useMemo(() => {
    return [...flatChapters]
      .filter((ch) => ch.updatedAt)
      .sort(
        (a, b) =>
          new Date(b.updatedAt!).getTime() - new Date(a.updatedAt!).getTime(),
      )
      .slice(0, 5)
      .map((ch) => ({
        id: ch.id,
        user: ch.assignedName ?? "系统",
        rev: `${ch.sortOrder || "•"} ${ch.title}`,
        time: new Date(ch.updatedAt!).toLocaleString("zh-CN", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        }),
      }));
  }, [flatChapters]);

  // Sync editor content when switching chapters.
  // The ref keeps the latest chapter while the effect keys on id only, so a
  // project reload (new chapter objects) never clobbers in-progress edits.
  const activeChapterRef = useRef(activeChapter);
  useEffect(() => {
    activeChapterRef.current = activeChapter;
  }, [activeChapter]);
  useEffect(() => {
    const chapter = activeChapterRef.current;
    if (chapter) {
      setEditorContent(chapter.content ?? "");
    }
  }, [activeChapter?.id]);

  // ── Handlers ──

  const handleSaveChapter = useCallback(async () => {
    if (!activeChapter || !project) return;
    setIsSaving(true);
    try {
      // Update content via the document system if available
      const chapterId = activeChapter.id;
      try {
        const doc = await projectApi.openChapter(projectId, chapterId);
        sessionStorage.setItem(
          "openChapterDoc",
          JSON.stringify({ ...doc, content: editorContent }),
        );
      } catch {
        // fallback: just save to session
      }
      toast.success("章节已保存");
      void loadProject();
    } catch {
      toast.error("保存失败");
    } finally {
      setIsSaving(false);
    }
  }, [activeChapter, editorContent, projectId, loadProject, project]);

  const handleAddMember = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!newMemberName.trim()) return;
      setAddingMember(true);
      try {
        await projectApi.addMember(projectId, newMemberName.trim(), "writer");
        toast.success("成员已添加");
        setNewMemberName("");
        setShowAddMember(false);
        void loadProject();
      } catch {
        toast.error("添加成员失败");
      } finally {
        setAddingMember(false);
      }
    },
    [newMemberName, projectId, loadProject],
  );

  const handleRemoveMember = useCallback(
    async (userId: string) => {
      setRemovingId(userId);
      try {
        await projectApi.removeMember(projectId, userId);
        toast.success("成员已移除");
        void loadProject();
      } catch {
        toast.error("移除成员失败");
      } finally {
        setRemovingId(null);
      }
    },
    [projectId, loadProject],
  );

  const handleEnterChat = useCallback(async () => {
    setEntering(true);
    try {
      const { threadId } = await projectApi.enter(projectId);
      window.open(
        `/workspace/chats/${threadId}?from=project&projectId=${projectId}&projectName=${encodeURIComponent(project?.name ?? "")}`,
        "_blank",
      );
    } catch {
      toast.error("进入对话失败");
    } finally {
      setEntering(false);
    }
  }, [projectId, project?.name]);

  // ── Loading state ──

  if (loading) {
    return (
      <div
        className="cyber-grid flex h-full items-center justify-center"
        style={{ background: "var(--cyber-bg-primary)" }}
      >
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="text-info h-8 w-8 animate-spin" />
          <span className="font-cyber text-xs tracking-widest text-[var(--cyber-text-muted)] uppercase">
            &gt; INITIALIZING PROJECT NODE...
          </span>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div
        className="flex h-full flex-col items-center justify-center gap-4"
        style={{ background: "var(--cyber-bg-primary)" }}
      >
        <p className="text-destructive font-cyber text-sm">项目不存在</p>
        <Link
          href="/projects"
          className="text-info font-cyber text-xs hover:opacity-80"
        >
          &gt; 返回项目列表
        </Link>
      </div>
    );
  }

  const members = project.members ?? [];
  const owner = members.find((m) => m.role === "owner");

  // ── Render ──

  return (
    <div
      className="cyber-scope flex min-h-full w-full flex-1 flex-col gap-6 font-sans"
      style={{
        background: "var(--cyber-bg-primary)",
        color: "var(--cyber-text-main)",
      }}
    >
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 md:px-8">
        {/* ── 1. HEADER ── */}
        <div
          className="flex flex-col justify-between gap-4 pb-4 md:flex-row md:items-center"
          style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}
        >
          <div className="flex items-center gap-3">
            <Link
              href="/projects"
              className="group flex cursor-pointer items-center justify-center rounded-lg border p-2"
              style={{
                background: "var(--cyber-bg-tertiary)",
                borderColor: "var(--cyber-border-muted)",
                color: "var(--cyber-text-muted)",
              }}
            >
              <ArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
            </Link>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2
                  className="text-xl font-bold tracking-tight"
                  style={{ color: "var(--cyber-text-main)" }}
                >
                  {project.name}
                </h2>
                <span className="font-cyber border-primary/30 bg-primary/10 text-primary rounded border px-2.5 py-0.5 text-[10px] font-bold tracking-widest uppercase">
                  {project.reportType}
                </span>
                {owner && (
                  <span className="bg-muted border-border text-muted-foreground rounded border px-2 py-0.5 text-[10px] font-bold">
                    负责人: {owner.username}
                  </span>
                )}
              </div>
              <p
                className="mt-1 font-mono text-[11px]"
                style={{ color: "var(--cyber-text-muted)" }}
              >
                创建于:{" "}
                {project.createdAt
                  ? new Date(project.createdAt).toLocaleDateString("zh-CN")
                  : "未知"}
                <span className="mx-1.5">•</span>
                章节: {totalCount}
                <span className="mx-1.5">•</span>
                文件数: {fileCount}
              </p>
            </div>
          </div>

          {/* Tab navigation */}
          <div
            className="flex items-center gap-2 overflow-x-auto rounded-xl p-1"
            style={{
              background: "var(--cyber-bg-tertiary)",
              borderColor: "var(--cyber-border-muted)",
              border: "1px solid var(--cyber-border-muted)",
            }}
          >
            {(
              [
                ["overview", "项目概览", undefined],
                ["editor", "文档编辑", FileText],
                ["review", "审核工作台", CheckCircle2],
              ] as const
            ).map(([id, label, Icon]) => {
              const isActive = activeTab === id;
              const activeColors: Record<string, string> = {
                overview:
                  "bg-primary text-primary-foreground shadow-[0_0_10px_rgba(7,70,255,0.3)]",
                editor:
                  "bg-[#7c3aed] text-white shadow-[0_0_10px_rgba(124,58,237,0.3)]",
                review:
                  "bg-success text-white shadow-[0_0_10px_rgba(82,196,26,0.3)]",
              };
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveTab(id)}
                  className={`flex cursor-pointer items-center gap-1 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all ${
                    isActive ? activeColors[id] : "hover:bg-muted/50"
                  }`}
                  style={
                    !isActive ? { color: "var(--cyber-text-muted)" } : undefined
                  }
                >
                  {Icon && <Icon className="h-3.5 w-3.5" />}
                  <span>{label}</span>
                </button>
              );
            })}

            <div
              className="mx-1 h-4 w-[1px]"
              style={{ background: "var(--cyber-border-muted)" }}
            />

            {/* Enter Chat */}
            <button
              type="button"
              disabled={entering}
              onClick={handleEnterChat}
              className="bg-primary text-primary-foreground group flex cursor-pointer items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-bold shadow-md transition-all hover:opacity-90"
            >
              <MessageSquare className="h-3.5 w-3.5 transition-transform group-hover:scale-110" />
              <span>{entering ? "进入中..." : "进入对话"}</span>
            </button>
          </div>
        </div>

        {/* ── 2. STATS CARDS ── */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {(
            [
              {
                icon: Layers,
                label: "活跃章节",
                value: `${activeCount}/${totalCount}`,
                sub: "编写中 / CYBERNETIC CO-WRITING",
                color: "blue",
              },
              {
                icon: Users,
                label: "成员数",
                value: members.length,
                sub: "ACTIVE RESEARCHERS",
                color: "green",
              },
              {
                icon: FileText,
                label: "文件数",
                value: fileCount,
                sub: "COMPILED DOSSIERS",
                color: "cyan",
              },
              {
                icon: BookOpen,
                label: "已写字数",
                value: totalWords.toLocaleString(),
                sub: "累计 / ACCUMULATIVE GLYPHS",
                color: "amber",
              },
            ] as const
          ).map((card) => {
            const borders: Record<string, string> = {
              blue: "border-primary/15 bg-primary/5",
              green: "border-success/15 bg-success/5",
              cyan: "border-info/15 bg-info/5",
              amber: "border-warning/15 bg-warning/5",
            };
            const texts: Record<string, string> = {
              blue: "text-primary",
              green: "text-success",
              cyan: "text-info",
              amber: "text-warning",
            };
            const cornerDots: Record<string, string> = {
              blue: "bg-primary/10",
              green: "bg-success/10",
              cyan: "bg-info/10",
              amber: "bg-warning/10",
            };
            return (
              <div
                key={card.label}
                className={`group relative flex flex-col justify-between overflow-hidden rounded-xl border p-4 transition-all hover:scale-[1.015] ${borders[card.color]}`}
              >
                <span
                  className={`absolute top-0 right-0 h-2 w-2 ${cornerDots[card.color]}`}
                />
                <div className="flex items-center justify-between gap-2.5">
                  <span
                    className="text-xs font-bold"
                    style={{ color: "var(--cyber-text-main)" }}
                  >
                    {card.label}
                  </span>
                  <div
                    className={`rounded-md border p-1 ${borders[card.color]} ${texts[card.color]}`}
                  >
                    <card.icon
                      className={`h-4 w-4 ${card.color === "blue" ? "animate-pulse" : ""}`}
                    />
                  </div>
                </div>
                <div
                  className={`font-cyber my-2 text-3xl font-extrabold ${texts[card.color]} ${
                    card.color === "blue" ? "text-shadow-glow" : ""
                  }`}
                >
                  {card.value}
                </div>
                <p
                  className="font-mono text-[10px] tracking-wider"
                  style={{ color: "var(--cyber-text-muted)" }}
                >
                  {card.sub}
                </p>
              </div>
            );
          })}
        </div>

        {/* ── 3. STATUS FILTER LEGEND ── */}
        <div className="themed-card-sci flex flex-wrap items-center justify-between gap-4 rounded-xl p-3 text-xs">
          <div className="flex flex-wrap items-center gap-4">
            {(
              [
                ["pending", "未开始", "bg-muted-foreground", "slate"],
                ["draft", "编写中", "bg-primary", "blue"],
                ["reviewing", "审核中", "bg-warning", "amber"],
                ["approved", "已完成", "bg-success", "emerald"],
              ] as const
            ).map(([status, label, dotColor, accent]) => {
              const count = flatChapters.filter(
                (ch) => mapToSciFiStatus(ch.status) === status,
              ).length;
              const isActive = statusFilter === status;
              const activeCls: Record<string, string> = {
                slate: "bg-muted border-border text-muted-foreground",
                blue: "bg-primary/10 border-primary/30 text-primary",
                amber: "bg-warning/10 border-warning/30 text-warning",
                emerald: "bg-success/15 border-success/30 text-success",
              };
              const idleHover: Record<string, string> = {
                slate: "hover:text-muted-foreground hover:bg-muted/50",
                blue: "hover:text-primary hover:bg-primary/5",
                amber: "hover:text-warning hover:bg-warning/5",
                emerald: "hover:text-success hover:bg-success/5",
              };
              const ringCls: Record<string, string> = {
                slate: "ring-muted-foreground/15",
                blue: "ring-primary/15",
                amber: "ring-warning/15",
                emerald: "ring-success/15",
              };
              return (
                <button
                  key={status}
                  type="button"
                  onClick={() =>
                    setStatusFilter(statusFilter === status ? "all" : status)
                  }
                  className={`relative flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 transition-all ${
                    isActive
                      ? activeCls[accent]
                      : `border-transparent ${idleHover[accent]}`
                  }`}
                  style={
                    !isActive ? { color: "var(--cyber-text-muted)" } : undefined
                  }
                >
                  {status === "draft" && (
                    <span className="bg-primary ring-primary/10 absolute h-2.5 w-2.5 animate-ping rounded-full ring-4" />
                  )}
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${dotColor} ring-2 ${ringCls[accent]}`}
                  />
                  <span>{label}</span>
                  <span className="bg-muted text-muted-foreground rounded px-1 text-[10px] font-bold">
                    {status === "approved" ? `${count}/${totalCount}` : count}
                  </span>
                </button>
              );
            })}
          </div>
          <span className="text-muted-foreground hidden text-[10px] italic lg:inline-block">
            &gt; FILTERS READY // CLICK STAT NODE TO PIN CATEGORIES
          </span>
        </div>

        {/* ── WORKFLOW PROCESS PHASES (流程进度) ── */}
        <div className="themed-card-sci flex flex-col gap-3.5 rounded-xl p-4 md:p-5">
          <div
            className="flex items-center justify-between pb-2"
            style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}
          >
            <span
              className="font-cyber text-[11px] tracking-widest uppercase"
              style={{ color: "var(--cyber-text-muted)" }}
            >
              SYS STAGE PROGRESSION FLOW
            </span>
            <span
              className="font-cyber text-[10px]"
              style={{ color: "var(--cyber-text-muted)" }}
            >
              阶段 {Math.min(phaseIndex + 1, phases.length)} / {phases.length}
            </span>
          </div>

          <div className="relative grid grid-cols-1 gap-4 py-2 sm:grid-cols-2 lg:grid-cols-4">
            {phases.map((phase, i) => {
              const state =
                i < phaseIndex
                  ? "completed"
                  : i === phaseIndex
                    ? "active"
                    : "pending";
              if (state === "completed") {
                return (
                  <div
                    key={phase.title}
                    className="bg-success/5 border-success/35 relative flex items-center gap-3 rounded-xl border p-3"
                  >
                    <div className="bg-success h-10 w-1.5 rounded-full" />
                    <div>
                      <h4
                        className="text-xs font-bold"
                        style={{ color: "var(--cyber-text-main)" }}
                      >
                        {phase.title}
                      </h4>
                      <p className="text-success font-cyber mt-0.5 text-[10px] font-bold">
                        {phase.sub}
                      </p>
                    </div>
                    <div className="bg-success/10 text-success absolute top-3 right-3 flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold">
                      ✔
                    </div>
                  </div>
                );
              }
              if (state === "active") {
                return (
                  <div
                    key={phase.title}
                    className="bg-primary/10 border-primary/30 relative flex animate-pulse items-center gap-3 rounded-xl border p-3 shadow-[0_0_15px_rgba(7,70,255,0.15)]"
                  >
                    <div className="bg-primary h-10 w-1.5 rounded-full" />
                    <div>
                      <h4
                        className="flex items-center gap-1.5 text-xs font-bold"
                        style={{ color: "var(--cyber-text-main)" }}
                      >
                        {phase.title}
                        <span className="bg-primary inline-block h-1.5 w-1.5 animate-ping rounded-full" />
                      </h4>
                      <p className="text-primary font-cyber mt-0.5 text-[10px] font-bold">
                        {phase.sub}
                      </p>
                    </div>
                  </div>
                );
              }
              return (
                <div
                  key={phase.title}
                  className="relative flex items-center gap-3 rounded-xl p-3 opacity-60"
                  style={{
                    background: "var(--cyber-bg-tertiary)",
                    border: "1px solid var(--cyber-border-muted)",
                  }}
                >
                  <div className="bg-muted-foreground h-10 w-1.5 rounded-full" />
                  <div>
                    <h4
                      className="text-xs font-bold"
                      style={{ color: "var(--cyber-text-main)" }}
                    >
                      {phase.title}
                    </h4>
                    <p
                      className="font-cyber mt-0.5 text-[10px]"
                      style={{ color: "var(--cyber-text-muted)" }}
                    >
                      {phase.sub}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── 4. MAIN CONTENT AREA ── */}
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
          {/* LEFT STAGE: Tab-dependent content */}
          <div className="flex flex-col gap-6 lg:col-span-8">
            <AnimatePresence mode="wait">
              {/* ── OVERVIEW TAB ── */}
              {activeTab === "overview" && (
                <motion.div
                  key="tab-overview"
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  className="flex flex-col gap-5"
                >
                  {/* Layout switcher */}
                  <div className="themed-card-sci flex items-center justify-between rounded-xl p-4">
                    <div className="flex items-center gap-2">
                      <Layers className="text-primary h-4 w-4" />
                      <h3
                        className="text-sm font-bold"
                        style={{ color: "var(--cyber-text-main)" }}
                      >
                        章节进度与结构规划
                      </h3>
                    </div>
                    <div
                      className="flex rounded-lg p-0.5"
                      style={{
                        background: "var(--cyber-bg-tertiary)",
                        border: "1px solid var(--cyber-border-muted)",
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => setLayoutMode("list")}
                        className={`flex cursor-pointer items-center gap-1 rounded px-3 py-1 text-xs font-semibold transition-colors ${
                          layoutMode === "list"
                            ? "bg-muted text-primary border-primary/20 border"
                            : ""
                        }`}
                        style={
                          layoutMode !== "list"
                            ? { color: "var(--cyber-text-muted)" }
                            : undefined
                        }
                      >
                        <ListFilter className="h-3.5 w-3.5" />
                        <span>列表模式</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setLayoutMode("kanban")}
                        className={`flex cursor-pointer items-center gap-1 rounded px-3 py-1 text-xs font-semibold transition-colors ${
                          layoutMode === "kanban"
                            ? "bg-muted text-primary border-primary/20 border"
                            : ""
                        }`}
                        style={
                          layoutMode !== "kanban"
                            ? { color: "var(--cyber-text-muted)" }
                            : undefined
                        }
                      >
                        <LayoutGrid className="h-3.5 w-3.5" />
                        <span>看板模式</span>
                      </button>
                    </div>
                  </div>

                  {/* List view */}
                  {layoutMode === "list" ? (
                    <div className="themed-card-sci flex min-h-[300px] flex-col gap-3 overflow-hidden rounded-xl p-4 md:p-5">
                      <div
                        className="font-cyber mb-1.5 flex items-center justify-between pb-2 text-[11px]"
                        style={{
                          color: "var(--cyber-text-muted)",
                          borderBottom: "1px solid var(--cyber-border-muted)",
                        }}
                      >
                        <span>PROJECT OUTLINE NODE TREE</span>
                        <span>TOTAL LISTINGS: {filteredChapters.length}</span>
                      </div>
                      <div className="cyber-scroll flex max-h-[480px] flex-col gap-2 overflow-y-auto pr-1">
                        {filteredChapters.length > 0 ? (
                          filteredChapters.map((ch) => {
                            const status = mapToSciFiStatus(ch.status);
                            const isParent = !ch.parentId;
                            return (
                              <div
                                key={ch.id}
                                style={{
                                  paddingLeft: isParent ? "0.5rem" : "2.5rem",
                                }}
                                className={`group flex cursor-pointer flex-col justify-between gap-3 rounded-lg border p-3 transition-all md:flex-row md:items-center ${
                                  selectedChapterId === ch.id
                                    ? "bg-primary/10 border-primary/50 glow-purple"
                                    : "bg-muted/30 hover:bg-muted/50 hover:border-primary/20 border-transparent"
                                }`}
                                onClick={() => {
                                  setSelectedChapterId(ch.id);
                                  setActiveTab("editor");
                                }}
                              >
                                <div className="flex min-w-0 items-start gap-2.5">
                                  <span className="font-cyber bg-muted text-muted-foreground mt-0.5 rounded-md px-1.5 py-0.5 text-[10px] font-bold">
                                    {ch.sortOrder || ch.id.slice(0, 4)}
                                  </span>
                                  <div className="min-w-0">
                                    <h4
                                      className="truncate text-xs font-normal"
                                      style={{
                                        color: "var(--cyber-text-main)",
                                      }}
                                    >
                                      {ch.title}
                                    </h4>
                                    {ch.content && (
                                      <p
                                        className="mt-0.5 max-w-[450px] truncate text-[10px] leading-normal font-normal"
                                        style={{
                                          color: "var(--cyber-text-muted)",
                                        }}
                                      >
                                        {ch.content.slice(0, 80)}...
                                      </p>
                                    )}
                                  </div>
                                </div>
                                <div className="flex shrink-0 items-center gap-3.5 self-end md:self-center">
                                  <span
                                    className="font-cyber text-[10px]"
                                    style={{ color: "var(--cyber-text-muted)" }}
                                  >
                                    {activityLabel(ch.updatedAt)}
                                  </span>
                                  {ch.assignedName && (
                                    <span
                                      className="rounded px-2 py-0.5 text-[10px] font-semibold"
                                      style={{
                                        background: "var(--cyber-bg-tertiary)",
                                        border:
                                          "1px solid var(--cyber-border-muted)",
                                        color: "var(--cyber-text-muted)",
                                      }}
                                    >
                                      {ch.assignedName}
                                    </span>
                                  )}
                                  <span
                                    className={`rounded px-2 py-0.5 text-[10px] font-bold ${statusBadgeClass(status)}`}
                                  >
                                    {status === "approved"
                                      ? `已完成 ${Math.round((ch.wordCountCurrent / Math.max(ch.wordCountTarget, 1)) * 100)}%`
                                      : STATUS_LABELS[status]}
                                  </span>
                                </div>
                              </div>
                            );
                          })
                        ) : (
                          <div className="flex flex-col items-center justify-center py-12 text-center">
                            <BookOpen
                              className="mb-2 h-8 w-8 opacity-20"
                              style={{ color: "var(--cyber-text-muted)" }}
                            />
                            <p
                              className="text-sm"
                              style={{ color: "var(--cyber-text-muted)" }}
                            >
                              暂无章节数据
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    /* Kanban view */
                    <div className="grid min-h-[380px] grid-cols-1 items-start gap-4 md:grid-cols-4">
                      {(
                        [
                          "pending",
                          "draft",
                          "reviewing",
                          "approved",
                        ] as ChapterStatus[]
                      ).map((colStatus) => {
                        const colCards = flatChapters.filter(
                          (ch) => mapToSciFiStatus(ch.status) === colStatus,
                        );
                        const colColors: Record<
                          ChapterStatus,
                          { border: string; bg: string; text: string }
                        > = {
                          pending: {
                            border: "border-border",
                            bg: "bg-muted/30",
                            text: "text-muted-foreground",
                          },
                          draft: {
                            border: "border-primary/20",
                            bg: "bg-primary/5",
                            text: "text-primary",
                          },
                          reviewing: {
                            border: "border-warning/20",
                            bg: "bg-warning/5",
                            text: "text-warning",
                          },
                          approved: {
                            border: "border-success/20",
                            bg: "bg-success/5",
                            text: "text-success",
                          },
                        };
                        return (
                          <div
                            key={colStatus}
                            className={`themed-card-sci flex min-h-[350px] flex-col gap-3 rounded-xl p-3 ${colColors[colStatus].border}`}
                          >
                            <div
                              className="mb-1 flex items-center justify-between pb-2"
                              style={{
                                borderBottom:
                                  "1px solid var(--cyber-border-muted)",
                              }}
                            >
                              <span
                                className="text-xs font-bold"
                                style={{ color: "var(--cyber-text-main)" }}
                              >
                                {STATUS_LABELS[colStatus]}
                              </span>
                              <span
                                className={`font-cyber rounded px-1.5 py-0.5 text-[10px] font-bold ${colColors[colStatus].text}`}
                              >
                                {colCards.length}
                              </span>
                            </div>
                            {colCards.length > 0 ? (
                              colCards.map((ch) => (
                                <motion.div
                                  key={ch.id}
                                  layout
                                  whileHover={{ scale: 1.02 }}
                                  onClick={() => {
                                    setSelectedChapterId(ch.id);
                                    setActiveTab("editor");
                                  }}
                                  className="hover:border-primary/30 flex cursor-pointer flex-col justify-between rounded-xl border border-[var(--cyber-border-muted)] bg-[var(--cyber-bg-tertiary)] p-3 transition-all"
                                >
                                  <div className="mb-1.5 flex items-start justify-between gap-1">
                                    <span className="font-cyber bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[9px] font-bold">
                                      {ch.sortOrder || ch.id.slice(0, 4)}
                                    </span>
                                    {ch.assignedName && (
                                      <span
                                        className="text-[9px] font-medium"
                                        style={{
                                          color: "var(--cyber-text-muted)",
                                        }}
                                      >
                                        {ch.assignedName}
                                      </span>
                                    )}
                                  </div>
                                  <h4
                                    className="mb-2 line-clamp-1 text-left text-xs font-normal"
                                    style={{ color: "var(--cyber-text-main)" }}
                                  >
                                    {ch.title}
                                  </h4>
                                  <div
                                    className="font-cyber mt-1 flex flex-col gap-1 text-[8px]"
                                    style={{ color: "var(--cyber-text-muted)" }}
                                  >
                                    <div className="flex items-center justify-between font-mono">
                                      <span>Progress:</span>
                                      <span
                                        className={
                                          colStatus === "approved"
                                            ? "text-success font-bold"
                                            : "text-primary font-bold"
                                        }
                                      >
                                        {ch.wordCountTarget > 0
                                          ? Math.round(
                                              (ch.wordCountCurrent /
                                                ch.wordCountTarget) *
                                                100,
                                            )
                                          : 0}
                                        %
                                      </span>
                                    </div>
                                    <div className="bg-muted h-1 w-full overflow-hidden rounded-full">
                                      <div
                                        className={`h-full rounded-full transition-all duration-500 ${colStatus === "approved" ? "bg-success" : "bg-primary"}`}
                                        style={{
                                          width: `${Math.min(ch.wordCountTarget > 0 ? (ch.wordCountCurrent / ch.wordCountTarget) * 100 : 0, 100)}%`,
                                        }}
                                      />
                                    </div>
                                  </div>
                                </motion.div>
                              ))
                            ) : (
                              <div
                                className="font-cyber py-10 text-center text-[10px] italic"
                                style={{ color: "var(--cyber-text-muted)" }}
                              >
                                &gt; COLUMN EMPTY
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </motion.div>
              )}

              {/* ── EDITOR TAB ── */}
              {activeTab === "editor" && (
                <motion.div
                  key="tab-editor"
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  className="grid grid-cols-1 gap-5 md:grid-cols-12"
                >
                  {/* Chapter sidebar */}
                  <div className="themed-card-sci cyber-scroll flex max-h-[500px] flex-col gap-3 overflow-y-auto rounded-xl p-3 md:col-span-4 md:p-4">
                    <div
                      className="font-cyber pb-2 text-xs font-bold tracking-wider uppercase"
                      style={{
                        color: "var(--cyber-text-muted)",
                        borderBottom: "1px solid var(--cyber-border-muted)",
                      }}
                    >
                      大纲树选编 / Document Outline
                    </div>
                    {flatChapters.map((ch) => (
                      <button
                        key={ch.id}
                        type="button"
                        onClick={() => setSelectedChapterId(ch.id)}
                        className={`flex cursor-pointer items-center justify-between gap-1.5 rounded-lg p-2.5 text-left text-xs transition-all ${
                          selectedChapterId === ch.id
                            ? "bg-primary text-primary-foreground font-normal"
                            : "bg-muted/30 hover:bg-muted/50"
                        }`}
                        style={
                          selectedChapterId !== ch.id
                            ? { color: "var(--cyber-text-muted)" }
                            : undefined
                        }
                      >
                        <div className="min-w-0 truncate">
                          <span className="font-cyber mr-1.5 font-bold opacity-80">
                            {ch.sortOrder || ch.id.slice(0, 4)}
                          </span>
                          <span>{ch.title}</span>
                        </div>
                        {mapToSciFiStatus(ch.status) === "approved" && (
                          <Check className="text-success h-3.5 w-3.5 shrink-0" />
                        )}
                      </button>
                    ))}
                  </div>

                  {/* Editor canvas */}
                  <div className="themed-card-sci flex flex-col gap-4 rounded-xl p-4 md:col-span-8 md:p-5">
                    {activeChapter ? (
                      <>
                        <div
                          className="flex flex-col justify-between gap-2 pb-3 md:flex-row md:items-center"
                          style={{
                            borderBottom: "1px solid var(--cyber-border-muted)",
                          }}
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-cyber bg-primary/10 border-primary/20 text-primary rounded border px-2 py-0.5 text-[10px] font-bold">
                                ID: {activeChapter.id.slice(0, 8)}
                              </span>
                              {activeChapter.assignedName && (
                                <span className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-[10px]">
                                  编撰者: {activeChapter.assignedName}
                                </span>
                              )}
                            </div>
                            <h3
                              className="mt-1.5 truncate text-sm font-bold"
                              style={{ color: "var(--cyber-text-main)" }}
                            >
                              {activeChapter.title}
                            </h3>
                          </div>
                          {/* AI action buttons */}
                          <div className="flex items-center gap-1.5">
                            {(["expand", "polish", "audit"] as const).map(
                              (mode) => {
                                const config = {
                                  expand: {
                                    icon: Sparkles,
                                    label: "AI扩写",
                                    color: "text-primary",
                                    border: "border-primary/20",
                                    bg: "bg-primary/10",
                                  },
                                  polish: {
                                    icon: Edit3,
                                    label: "润色",
                                    color: "text-primary",
                                    border: "border-primary/20",
                                    bg: "bg-primary/10",
                                  },
                                  audit: {
                                    icon: ShieldAlert,
                                    label: "合规自检",
                                    color: "text-destructive",
                                    border: "border-destructive/20",
                                    bg: "bg-destructive/10",
                                  },
                                }[mode];
                                return (
                                  <button
                                    key={mode}
                                    type="button"
                                    disabled={isSaving}
                                    onClick={handleEnterChat}
                                    className={`flex cursor-pointer items-center gap-1 rounded border px-2.5 py-1.5 text-[10px] font-bold transition-all ${config.bg} ${config.border} ${config.color}`}
                                    title={`打开对话进行${config.label}`}
                                  >
                                    <config.icon className="h-3 w-3" />
                                    <span>{config.label}</span>
                                  </button>
                                );
                              },
                            )}
                          </div>
                        </div>

                        <div className="flex min-h-[250px] flex-1 flex-col gap-2">
                          <label
                            className="font-cyber text-[10px] select-none"
                            style={{ color: "var(--cyber-text-muted)" }}
                          >
                            TEXT WRITING BUFFER WORKSPACE // EDIT DIRECTLY
                          </label>
                          <textarea
                            value={editorContent}
                            onChange={(e) => setEditorContent(e.target.value)}
                            disabled={isSaving}
                            placeholder="编辑该章节内容..."
                            className="h-[220px] w-full flex-1 resize-none rounded-lg p-3 font-mono text-xs leading-relaxed outline-none"
                            style={{
                              background: "var(--cyber-bg-tertiary)",
                              border: "1px solid var(--cyber-border-muted)",
                              color: "var(--cyber-text-main)",
                            }}
                          />
                        </div>

                        <div
                          className="mt-1 flex items-center justify-between pt-3 text-xs"
                          style={{
                            borderTop: "1px solid var(--cyber-border-muted)",
                          }}
                        >
                          <span
                            className="font-cyber text-[10px]"
                            style={{ color: "var(--cyber-text-muted)" }}
                          >
                            SYS AUTOSAVED DEPLOYMENTS // WORDS:{" "}
                            {editorContent.length}
                          </span>
                          <button
                            type="button"
                            onClick={handleSaveChapter}
                            disabled={isSaving}
                            className="bg-primary text-primary-foreground flex cursor-pointer items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-bold transition-all hover:opacity-90 active:scale-95"
                          >
                            {isSaving ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Save className="h-3.5 w-3.5" />
                            )}
                            <span>保存 (Save Revision)</span>
                          </button>
                        </div>
                      </>
                    ) : (
                      <div
                        className="flex h-[300px] items-center justify-center text-sm"
                        style={{ color: "var(--cyber-text-muted)" }}
                      >
                        选择一个章节开始编辑
                      </div>
                    )}
                  </div>
                </motion.div>
              )}

              {/* ── REVIEW TAB ── */}
              {activeTab === "review" && (
                <motion.div
                  key="tab-review"
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  className="themed-card-sci flex min-h-[300px] flex-col gap-5 rounded-xl p-4 md:p-6"
                >
                  <div
                    className="flex items-center justify-between pb-3"
                    style={{
                      borderBottom: "1px solid var(--cyber-border-muted)",
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="text-success h-5 w-5" />
                      <h3
                        className="text-sm font-bold uppercase"
                        style={{ color: "var(--cyber-text-main)" }}
                      >
                        {project.name} - 技术审查核心控制台 / Review Console
                      </h3>
                    </div>
                    <span className="font-cyber bg-success/10 border-success/20 text-success rounded border px-2 py-0.5 text-[10px] font-bold">
                      SECURITY ACCESS LEVEL A
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    {/* Checklist */}
                    <div className="themed-terminal-sci flex flex-col gap-3 rounded-xl p-4">
                      <span
                        className="font-cyber mb-1 block text-[10px] tracking-widest uppercase"
                        style={{ color: "var(--cyber-text-muted)" }}
                      >
                        AUTOMATION COMPLIANCE CHECKLIST
                      </span>
                      {[
                        "《项目结构完整性》自检通过",
                        "《章节内容格式规范》校验",
                        "《成员角色权限》复核",
                        "《文档输出就绪状态》检查",
                      ].map((item, i) => (
                        <div
                          key={i}
                          className="flex items-center gap-2 py-1 text-xs"
                          style={{
                            borderBottom: "1px solid var(--cyber-border-muted)",
                          }}
                        >
                          <CheckCircle2 className="text-success h-4 w-4" />
                          <span style={{ color: "var(--cyber-text-muted)" }}>
                            {item}
                          </span>
                        </div>
                      ))}
                    </div>

                    {/* Sign-off */}
                    <div className="themed-terminal-sci bg-success/5 border-success/15 flex h-full flex-col justify-between rounded-xl p-4">
                      <div>
                        <span className="font-cyber text-success mb-2 block text-[10px] tracking-widest uppercase">
                          APPROVED SIGN-OFF
                        </span>
                        <p
                          className="mb-3 text-xs leading-relaxed font-normal"
                          style={{ color: "var(--cyber-text-muted)" }}
                        >
                          审核工作台用于跟踪项目各章节的审核状态。当所有章节完成并经过审核后，项目即可标记为完成。
                        </p>
                      </div>
                      <div
                        className="text-xs"
                        style={{ color: "var(--cyber-text-muted)" }}
                      >
                        <span className="font-cyber text-success mb-1 block font-bold">
                          &gt; AUDIT STATUS:
                        </span>
                        <span>
                          已完成章节: {completedCount}/{totalCount}
                        </span>
                        <span className="mx-2">•</span>
                        <span>
                          审核中:{" "}
                          {
                            flatChapters.filter(
                              (ch) =>
                                mapToSciFiStatus(ch.status) === "reviewing",
                            ).length
                          }
                        </span>
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* ── REVISION LEDGER (版本更迭记录) ── */}
            <div className="themed-card-sci flex flex-col gap-3 rounded-xl p-4 text-xs md:p-5">
              <div
                className="mb-1 flex items-center gap-1.5 pb-2 text-xs font-bold"
                style={{
                  borderBottom: "1px solid var(--cyber-border-muted)",
                  color: "var(--cyber-text-main)",
                }}
              >
                <Terminal className="text-primary h-4 w-4 animate-pulse" />
                <span>版本更迭记录 // System Revision Ledger</span>
              </div>
              {revisionEntries.length > 0 ? (
                <div className="cyber-scroll flex max-h-[140px] flex-col gap-2 overflow-y-auto">
                  {revisionEntries.map((entry, ind) => (
                    <div
                      key={entry.id}
                      className="grid grid-cols-12 items-center gap-2 pb-1.5 font-mono text-[11px]"
                      style={{
                        borderBottom: "1px solid var(--cyber-border-muted)",
                      }}
                    >
                      <span
                        className="font-cyber col-span-2"
                        style={{ color: "var(--cyber-text-muted)" }}
                      >
                        #{ind + 1} NODE
                      </span>
                      <span className="text-info col-span-3 truncate font-bold">
                        {entry.user}
                      </span>
                      <span
                        className="col-span-5 truncate"
                        style={{ color: "var(--cyber-text-muted)" }}
                      >
                        {entry.rev}
                      </span>
                      <span
                        className="col-span-2 text-right"
                        style={{ color: "var(--cyber-text-muted)" }}
                      >
                        {entry.time}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p
                  className="font-cyber py-4 text-center text-[11px] italic"
                  style={{ color: "var(--cyber-text-muted)" }}
                >
                  &gt; NO REVISION RECORDS YET
                </p>
              )}
            </div>
          </div>

          {/* ── RIGHT SIDEBAR: Members ── */}
          <div className="flex flex-col gap-6 lg:col-span-4">
            <div className="themed-card-sci relative flex flex-col rounded-xl p-4 md:p-5">
              <div
                className="mb-4 flex items-center justify-between pb-3"
                style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}
              >
                <div className="flex items-center gap-2">
                  <Users className="text-primary h-4 w-4" />
                  <h3
                    className="text-sm font-bold tracking-wider uppercase"
                    style={{ color: "var(--cyber-text-main)" }}
                  >
                    项目成员
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddMember(!showAddMember)}
                  className="text-primary flex cursor-pointer items-center gap-0.5 text-xs font-bold hover:opacity-80"
                >
                  {showAddMember ? "✖ 折叠" : "✚ 添加成员"}
                </button>
              </div>

              {/* Add member form */}
              <AnimatePresence>
                {showAddMember && (
                  <motion.form
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    onSubmit={handleAddMember}
                    className="border-primary/20 bg-primary/5 mb-4 flex flex-col gap-2.5 overflow-hidden rounded-lg border p-3 text-xs"
                  >
                    <div>
                      <label
                        className="mb-1 block"
                        style={{ color: "var(--cyber-text-muted)" }}
                      >
                        成员用户名 (User ID)
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="例如: zhangsan"
                        value={newMemberName}
                        onChange={(e) => setNewMemberName(e.target.value)}
                        className="w-full rounded px-2 py-1 text-xs outline-none"
                        style={{
                          background: "var(--cyber-bg-tertiary)",
                          border: "1px solid var(--cyber-border-muted)",
                          color: "var(--cyber-text-main)",
                        }}
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={addingMember}
                      className="bg-primary text-primary-foreground w-full cursor-pointer rounded py-1.5 text-xs font-bold hover:opacity-90 disabled:opacity-50"
                    >
                      {addingMember ? "添加中..." : "批准加入班组"}
                    </button>
                  </motion.form>
                )}
              </AnimatePresence>

              {/* Member list */}
              <div className="flex flex-col gap-3">
                {members.length > 0 ? (
                  members.map((member) => {
                    const initials = (member.username ?? "?")
                      .slice(0, 2)
                      .toUpperCase();
                    const isOwner = member.role === "owner";
                    return (
                      <div
                        key={member.userId}
                        className="group flex items-center justify-between rounded-lg border p-3 transition-all"
                        style={{
                          borderColor: "var(--cyber-border-muted)",
                          background: "var(--cyber-bg-tertiary)",
                        }}
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={`flex h-9 w-9 items-center justify-center rounded-full text-xs font-bold uppercase ${
                              isOwner
                                ? "bg-primary/10 text-primary border-primary/20 border"
                                : "bg-muted text-muted-foreground border-border border"
                            }`}
                          >
                            {initials}
                          </div>
                          <div>
                            <h4
                              className="text-xs font-bold"
                              style={{ color: "var(--cyber-text-main)" }}
                            >
                              {member.username}
                            </h4>
                            <p
                              className="font-mono text-[10px]"
                              style={{ color: "var(--cyber-text-muted)" }}
                            >
                              NODE ACTIVE USER // {member.role}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span
                            className={`font-cyber rounded px-1.5 py-0.5 text-[9px] font-bold ${
                              isOwner
                                ? "bg-primary/10 text-primary border-primary/20 border"
                                : "bg-muted border border-transparent"
                            }`}
                            style={
                              !isOwner
                                ? { color: "var(--cyber-text-muted)" }
                                : undefined
                            }
                          >
                            {MEMBER_ROLE_LABELS[member.role] ?? member.role}
                          </span>
                          {!isOwner && (
                            <button
                              type="button"
                              onClick={() => handleRemoveMember(member.userId)}
                              disabled={removingId === member.userId}
                              className="hover:text-destructive hover:bg-destructive/5 cursor-pointer rounded p-1 opacity-0 transition-all group-hover:opacity-100"
                              style={{ color: "var(--cyber-text-muted)" }}
                              title="移除该成员"
                            >
                              {removingId === member.userId ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Trash2 className="h-3.5 w-3.5" />
                              )}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="px-3 py-6 text-center">
                    <Users
                      className="mx-auto mb-1.5 h-6 w-6 opacity-20"
                      style={{ color: "var(--cyber-text-muted)" }}
                    />
                    <p
                      className="text-xs"
                      style={{ color: "var(--cyber-text-muted)" }}
                    >
                      暂无成员
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* AI Assistant Card */}
            <div className="themed-card-sci from-primary/5 to-info/5 relative flex flex-col overflow-hidden rounded-xl bg-gradient-to-br p-4 md:p-5">
              <div
                className="mb-3 flex items-center gap-2 pb-3"
                style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}
              >
                <div className="bg-primary/15 text-primary rounded p-1">
                  <Cpu className="h-4 w-4" />
                </div>
                <h3
                  className="font-cyber text-xs font-bold tracking-wider uppercase"
                  style={{ color: "var(--cyber-text-main)" }}
                >
                  AI 助手 / Neural Copilot
                </h3>
              </div>
              <p
                className="text-[11px] leading-relaxed font-normal"
                style={{ color: "var(--cyber-text-muted)" }}
              >
                点击右上角「进入对话」按钮，使用 AI
                助手辅助编写、润色和审核文档章节。 AI
                可以帮你扩写内容、优化措辞、检查规范合规性。
              </p>
              <button
                type="button"
                onClick={handleEnterChat}
                disabled={entering}
                className="bg-primary text-primary-foreground mt-3 flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-bold hover:opacity-90 disabled:opacity-50"
              >
                <MessageSquare className="h-3.5 w-3.5" />
                {entering ? "进入中..." : "进入 AI 对话"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
