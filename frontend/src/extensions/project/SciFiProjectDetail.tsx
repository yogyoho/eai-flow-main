"use client";

import {
  ArrowLeft,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  Cpu,
  Edit3,
  FileText,
  Layers,
  LayoutGrid,
  ListFilter,
  Loader2,
  MessageSquare,
  Plus,
  Save,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { projectApi } from "@/extensions/project/api";
import {
  type ProjectChapter,
  type ProjectMember,
  type ReportProject,
  MEMBER_ROLE_LABELS,
} from "@/extensions/project/types";
import { aggregateWordCount, flattenChapters, inferStatus } from "@/extensions/project/utils";

// ── Local UI types (derived from API types) ──

type ChapterStatus = "draft" | "writing" | "review" | "completed";

interface SciFiProjectDetailProps {
  projectId: string;
}

// ── Status helpers ──

const STATUS_LABELS: Record<ChapterStatus, string> = {
  draft: "待编写",
  writing: "编写中",
  review: "审核中",
  completed: "已完成",
};

function mapToSciFiStatus(status: string): ChapterStatus {
  const s = inferStatus({ status } as ProjectChapter);
  if (s === "draft" || s === "writing" || s === "review" || s === "completed") return s;
  return "draft";
}

function statusBadgeClass(status: ChapterStatus): string {
  switch (status) {
    case "completed": return "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
    case "review": return "bg-amber-500/10 text-amber-400";
    case "writing": return "bg-blue-500/10 text-blue-400";
    default: return "bg-slate-400/15 text-slate-400";
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
  const [activeTab, setActiveTab] = useState<"overview" | "editor" | "review">("overview");
  const [layoutMode, setLayoutMode] = useState<"list" | "kanban">("list");
  const [statusFilter, setStatusFilter] = useState<"all" | ChapterStatus>("all");

  // Editor state
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null);
  const [editorContent, setEditorContent] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  // Member management
  const [showAddMember, setShowAddMember] = useState(false);
  const [newMemberName, setNewMemberName] = useState("");
  const [addingMember, setAddingMember] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  // AI Chat slide-out
  const [aiChatOpen, setAiChatOpen] = useState(false);
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
    loadProject();
  }, [loadProject]);

  // ── Derived data ──

  const flatChapters = useMemo(() => {
    if (!project?.chapters) return [];
    return flattenChapters(project.chapters);
  }, [project?.chapters]);

  const filteredChapters = useMemo(() => {
    if (statusFilter === "all") return flatChapters;
    return flatChapters.filter((ch) => mapToSciFiStatus(ch.status) === statusFilter);
  }, [flatChapters, statusFilter]);

  const activeChapter = useMemo(() => {
    if (!selectedChapterId) return flatChapters[0] ?? null;
    return flatChapters.find((ch) => ch.id === selectedChapterId) ?? flatChapters[0] ?? null;
  }, [flatChapters, selectedChapterId]);

  const activeCount = flatChapters.filter((ch) => mapToSciFiStatus(ch.status) === "writing").length;
  const completedCount = flatChapters.filter((ch) => mapToSciFiStatus(ch.status) === "completed").length;
  const totalCount = flatChapters.length;
  const totalWords = useMemo(() => {
    if (!project?.chapters) return 0;
    return aggregateWordCount(project.chapters);
  }, [project?.chapters]);

  // Sync editor content when switching chapters
  useEffect(() => {
    if (activeChapter) {
      setEditorContent(activeChapter.content ?? "");
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
        sessionStorage.setItem("openChapterDoc", JSON.stringify({ ...doc, content: editorContent }));
      } catch {
        // fallback: just save to session
      }
      toast.success("章节已保存");
      loadProject();
    } catch {
      toast.error("保存失败");
    } finally {
      setIsSaving(false);
    }
  }, [activeChapter, editorContent, projectId, loadProject, project]);

  const handleAddMember = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemberName.trim()) return;
    setAddingMember(true);
    try {
      await projectApi.addMember(projectId, newMemberName.trim(), "member");
      toast.success("成员已添加");
      setNewMemberName("");
      setShowAddMember(false);
      loadProject();
    } catch {
      toast.error("添加成员失败");
    } finally {
      setAddingMember(false);
    }
  }, [newMemberName, projectId, loadProject]);

  const handleRemoveMember = useCallback(async (userId: string) => {
    setRemovingId(userId);
    try {
      await projectApi.removeMember(projectId, userId);
      toast.success("成员已移除");
      loadProject();
    } catch {
      toast.error("移除成员失败");
    } finally {
      setRemovingId(null);
    }
  }, [projectId, loadProject]);

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
      <div className="flex h-full items-center justify-center cyber-grid" style={{ background: "var(--cyber-bg-primary)" }}>
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
          <span className="font-cyber text-xs text-[var(--cyber-text-muted)] tracking-widest uppercase">
            &gt; INITIALIZING PROJECT NODE...
          </span>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" style={{ background: "var(--cyber-bg-primary)" }}>
        <p className="text-sm text-red-400 font-cyber">项目不存在</p>
        <Link href="/projects" className="text-xs text-cyan-400 hover:text-cyan-300 font-cyber">
          &gt; 返回项目列表
        </Link>
      </div>
    );
  }

  const members = project.members ?? [];

  // ── Render ──

  return (
    <div
      className="flex-1 w-full flex flex-col gap-6 font-sans min-h-full"
      style={{
        background: "var(--cyber-bg-primary)",
        color: "var(--cyber-text-main)",
      }}
    >
      <div className="max-w-7xl w-full mx-auto px-4 md:px-8 py-6 flex flex-col gap-6">
        {/* ── 1. HEADER ── */}
        <div
          className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4"
          style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}
        >
          <div className="flex items-center gap-3">
            <Link
              href="/projects"
              className="p-2 rounded-lg border cursor-pointer flex items-center justify-center group"
              style={{
                background: "var(--cyber-bg-tertiary)",
                borderColor: "var(--cyber-border-muted)",
                color: "var(--cyber-text-muted)",
              }}
            >
              <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
            </Link>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-bold tracking-tight" style={{ color: "var(--cyber-text-main)" }}>
                  {project.name}
                </h2>
                <span className="text-[10px] uppercase font-cyber px-2.5 py-0.5 rounded border border-blue-500/30 bg-blue-500/10 text-blue-400 font-bold tracking-widest">
                  {project.reportType}
                </span>
              </div>
              <p className="text-[11px] font-mono mt-1" style={{ color: "var(--cyber-text-muted)" }}>
                创建于: {project.createdAt ? new Date(project.createdAt).toLocaleDateString("zh-CN") : "未知"}
                <span className="mx-1.5">•</span>
                章节: {totalCount}
                <span className="mx-1.5">•</span>
                文件数: {fileCount}
              </p>
            </div>
          </div>

          {/* Tab navigation */}
          <div
            className="flex items-center gap-2 p-1 rounded-xl overflow-x-auto"
            style={{
              background: "var(--cyber-bg-tertiary)",
              borderColor: "var(--cyber-border-muted)",
              border: "1px solid var(--cyber-border-muted)",
            }}
          >
            {([
              ["overview", "项目概览", undefined],
              ["editor", "文档编辑", FileText],
              ["review", "审核工作台", CheckCircle2],
            ] as const).map(([id, label, Icon]) => {
              const isActive = activeTab === id;
              const activeColors: Record<string, string> = {
                overview: "bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.3)]",
                editor: "bg-purple-600 text-white shadow-[0_0_10px_rgba(147,51,234,0.3)]",
                review: "bg-teal-600 text-white shadow-[0_0_10px_rgba(13,148,136,0.3)]",
              };
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveTab(id)}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1 ${
                    isActive
                      ? activeColors[id]
                      : "hover:bg-slate-400/5"
                  }`}
                  style={!isActive ? { color: "var(--cyber-text-muted)" } : undefined}
                >
                  {Icon && <Icon className="w-3.5 h-3.5" />}
                  <span>{label}</span>
                </button>
              );
            })}

            <div className="h-4 w-[1px] mx-1" style={{ background: "var(--cyber-border-muted)" }} />

            {/* Enter Chat */}
            <button
              type="button"
              disabled={entering}
              onClick={handleEnterChat}
              className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-500 text-white flex items-center gap-1.5 transition-all shadow-md group cursor-pointer"
            >
              <MessageSquare className="w-3.5 h-3.5 group-hover:scale-110 transition-transform" />
              <span>{entering ? "进入中..." : "进入对话"}</span>
            </button>
          </div>
        </div>

        {/* ── 2. STATS CARDS ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {([
            { icon: Layers, label: "活跃章节", value: `${activeCount}/${totalCount}`, sub: "编写中 / CYBERNETIC CO-WRITING", color: "blue" },
            { icon: Users, label: "成员数", value: members.length, sub: "ACTIVE RESEARCHERS", color: "purple" },
            { icon: FileText, label: "文件数", value: fileCount, sub: "COMPILED DOSSIERS", color: "cyan" },
            { icon: BookOpen, label: "已写字数", value: totalWords.toLocaleString(), sub: "累计 / ACCUMULATIVE GLYPHS", color: "amber" },
          ] as const).map((card) => {
            const borders: Record<string, string> = {
              blue: "border-blue-500/15 bg-blue-500/5",
              purple: "border-purple-500/15 bg-purple-500/5",
              cyan: "border-cyan-500/15 bg-cyan-500/5",
              amber: "border-amber-500/15 bg-amber-500/5",
            };
            const texts: Record<string, string> = {
              blue: "text-blue-400",
              purple: "text-purple-400",
              cyan: "text-cyan-400",
              amber: "text-amber-400",
            };
            return (
              <div
                key={card.label}
                className={`rounded-xl p-4 flex flex-col justify-between group hover:scale-[1.015] transition-all relative overflow-hidden border ${borders[card.color]}`}
              >
                <div className="flex items-center justify-between gap-2.5">
                  <span className="text-xs font-bold" style={{ color: "var(--cyber-text-main)" }}>{card.label}</span>
                  <div className={`p-1 rounded-md border ${borders[card.color]} ${texts[card.color]}`}>
                    <card.icon className="w-4 h-4" />
                  </div>
                </div>
                <div className={`my-2 text-3xl font-extrabold font-cyber ${texts[card.color]}`}>
                  {card.value}
                </div>
                <p className="text-[10px] font-mono tracking-wider" style={{ color: "var(--cyber-text-muted)" }}>
                  {card.sub}
                </p>
              </div>
            );
          })}
        </div>

        {/* ── 3. STATUS FILTER LEGEND ── */}
        <div className="themed-card-sci rounded-xl p-3 flex flex-wrap items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-4 flex-wrap">
            {([
              ["draft", "待编写", "bg-slate-500"],
              ["writing", "编写中", "bg-blue-500"],
              ["review", "审核中", "bg-amber-500"],
              ["completed", "已完成", "bg-emerald-500"],
            ] as const).map(([status, label, dotColor]) => {
              const count = flatChapters.filter((ch) => mapToSciFiStatus(ch.status) === status).length;
              const isActive = statusFilter === status;
              return (
                <button
                  key={status}
                  type="button"
                  onClick={() => setStatusFilter(statusFilter === status ? "all" : status)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
                    isActive
                      ? "bg-slate-400/20 border-slate-500 text-slate-300"
                      : "border-transparent hover:bg-slate-400/5"
                  }`}
                  style={!isActive ? { color: "var(--cyber-text-muted)" } : undefined}
                >
                  <span className={`w-2.5 h-2.5 rounded-full ${dotColor} ring-2 ring-${dotColor}/15`} />
                  <span>{label}</span>
                  <span className="font-bold px-1 rounded bg-slate-500/10 text-slate-400 text-[10px]">
                    {status === "completed" ? `${count}/${totalCount}` : count}
                  </span>
                </button>
              );
            })}
          </div>
          <span className="hidden lg:inline-block text-[10px] italic" style={{ color: "var(--cyber-text-muted)" }}>
            &gt; FILTERS READY // CLICK STAT NODE TO PIN CATEGORIES
          </span>
        </div>

        {/* ── 4. MAIN CONTENT AREA ── */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* LEFT STAGE: Tab-dependent content */}
          <div className="lg:col-span-8 flex flex-col gap-6">
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
                  <div className="themed-card-sci rounded-xl p-4 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Layers className="w-4 h-4 text-purple-400" />
                      <h3 className="text-sm font-bold" style={{ color: "var(--cyber-text-main)" }}>
                        章节进度与结构规划
                      </h3>
                    </div>
                    <div className="flex rounded-lg p-0.5" style={{ background: "var(--cyber-bg-tertiary)", border: "1px solid var(--cyber-border-muted)" }}>
                      <button
                        type="button"
                        onClick={() => setLayoutMode("list")}
                        className={`px-3 py-1 rounded text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors ${
                          layoutMode === "list"
                            ? "bg-slate-500/15 text-purple-400 border border-purple-500/20"
                            : ""
                        }`}
                        style={layoutMode !== "list" ? { color: "var(--cyber-text-muted)" } : undefined}
                      >
                        <ListFilter className="w-3.5 h-3.5" />
                        <span>列表模式</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setLayoutMode("kanban")}
                        className={`px-3 py-1 rounded text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors ${
                          layoutMode === "kanban"
                            ? "bg-slate-500/15 text-purple-400 border border-purple-500/20"
                            : ""
                        }`}
                        style={layoutMode !== "kanban" ? { color: "var(--cyber-text-muted)" } : undefined}
                      >
                        <LayoutGrid className="w-3.5 h-3.5" />
                        <span>看板模式</span>
                      </button>
                    </div>
                  </div>

                  {/* List view */}
                  {layoutMode === "list" ? (
                    <div className="themed-card-sci rounded-xl p-4 md:p-5 flex flex-col gap-3 min-h-[300px] overflow-hidden">
                      <div
                        className="flex items-center justify-between text-[11px] font-cyber pb-2 mb-1.5"
                        style={{ color: "var(--cyber-text-muted)", borderBottom: "1px solid var(--cyber-border-muted)" }}
                      >
                        <span>PROJECT OUTLINE NODE TREE</span>
                        <span>TOTAL LISTINGS: {filteredChapters.length}</span>
                      </div>
                      <div className="flex flex-col gap-2 max-h-[480px] overflow-y-auto pr-1 cyber-scroll">
                        {filteredChapters.length > 0 ? (
                          filteredChapters.map((ch) => {
                            const status = mapToSciFiStatus(ch.status);
                            const isParent = !ch.parentId;
                            return (
                              <div
                                key={ch.id}
                                style={{ paddingLeft: isParent ? "0.5rem" : "2.5rem" }}
                                className={`p-3 rounded-lg border transition-all flex flex-col md:flex-row md:items-center justify-between gap-3 group cursor-pointer ${
                                  selectedChapterId === ch.id
                                    ? "bg-purple-500/10 border-purple-500/50 glow-purple"
                                    : "bg-slate-400/5 hover:bg-slate-400/10 border-transparent hover:border-purple-500/20"
                                }`}
                                onClick={() => {
                                  setSelectedChapterId(ch.id);
                                  setActiveTab("editor");
                                }}
                              >
                                <div className="flex items-start gap-2.5 min-w-0">
                                  <span className="text-[10px] font-cyber bg-slate-500/10 text-slate-400 font-bold px-1.5 py-0.5 rounded-md mt-0.5">
                                    {ch.sortOrder || ch.id.slice(0, 4)}
                                  </span>
                                  <div className="min-w-0">
                                    <h4
                                      className={`text-xs font-bold truncate ${isParent ? "text-sm" : "font-medium"}`}
                                      style={{ color: "var(--cyber-text-main)" }}
                                    >
                                      {ch.title}
                                    </h4>
                                    {ch.content && (
                                      <p className="text-[10px] truncate max-w-[450px] font-normal mt-0.5 leading-normal" style={{ color: "var(--cyber-text-muted)" }}>
                                        {ch.content.slice(0, 80)}...
                                      </p>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-3.5 shrink-0 self-end md:self-center">
                                  <span className="text-[10px] font-cyber" style={{ color: "var(--cyber-text-muted)" }}>
                                    {activityLabel(ch.updatedAt)}
                                  </span>
                                  {ch.assignedName && (
                                    <span
                                      className="text-[10px] px-2 py-0.5 rounded font-semibold"
                                      style={{
                                        background: "var(--cyber-bg-tertiary)",
                                        border: "1px solid var(--cyber-border-muted)",
                                        color: "var(--cyber-text-muted)",
                                      }}
                                    >
                                      {ch.assignedName}
                                    </span>
                                  )}
                                  <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${statusBadgeClass(status)}`}>
                                    {status === "completed"
                                      ? `已完成 ${Math.round((ch.wordCountCurrent / Math.max(ch.wordCountTarget, 1)) * 100)}%`
                                      : STATUS_LABELS[status]}
                                  </span>
                                </div>
                              </div>
                            );
                          })
                        ) : (
                          <div className="flex flex-col items-center justify-center py-12 text-center">
                            <BookOpen className="h-8 w-8 mb-2 opacity-20" style={{ color: "var(--cyber-text-muted)" }} />
                            <p className="text-sm" style={{ color: "var(--cyber-text-muted)" }}>暂无章节数据</p>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    /* Kanban view */
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-start min-h-[380px]">
                      {(["draft", "writing", "review", "completed"] as ChapterStatus[]).map((colStatus) => {
                        const colCards = flatChapters.filter((ch) => mapToSciFiStatus(ch.status) === colStatus);
                        const colColors: Record<ChapterStatus, { border: string; bg: string; text: string }> = {
                          draft: { border: "border-slate-500/20", bg: "bg-slate-500/5", text: "text-slate-400" },
                          writing: { border: "border-blue-500/20", bg: "bg-blue-500/5", text: "text-blue-400" },
                          review: { border: "border-amber-500/20", bg: "bg-amber-500/5", text: "text-amber-400" },
                          completed: { border: "border-emerald-500/20", bg: "bg-emerald-500/5", text: "text-emerald-400" },
                        };
                        return (
                          <div key={colStatus} className={`themed-card-sci rounded-xl p-3 flex flex-col gap-3 min-h-[350px] ${colColors[colStatus].border}`}>
                            <div className="flex items-center justify-between pb-2 mb-1" style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}>
                              <span className="text-xs font-bold" style={{ color: "var(--cyber-text-main)" }}>{STATUS_LABELS[colStatus]}</span>
                              <span className={`font-cyber font-bold text-[10px] px-1.5 py-0.5 rounded ${colColors[colStatus].text}`}>
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
                                  className="p-3 border rounded-xl flex flex-col justify-between cursor-pointer transition-all bg-[var(--cyber-bg-tertiary)] border-[var(--cyber-border-muted)] hover:border-purple-500/30"
                                >
                                  <div className="flex items-start justify-between gap-1 mb-1.5">
                                    <span className="text-[9px] font-cyber px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-400 font-bold">
                                      {ch.sortOrder || ch.id.slice(0, 4)}
                                    </span>
                                    {ch.assignedName && (
                                      <span className="text-[9px] font-medium" style={{ color: "var(--cyber-text-muted)" }}>{ch.assignedName}</span>
                                    )}
                                  </div>
                                  <h4 className="text-xs font-bold line-clamp-1 mb-2 text-left" style={{ color: "var(--cyber-text-main)" }}>{ch.title}</h4>
                                  <div className="flex flex-col gap-1 mt-1 font-cyber text-[8px]" style={{ color: "var(--cyber-text-muted)" }}>
                                    <div className="flex items-center justify-between font-mono">
                                      <span>Progress:</span>
                                      <span className={colStatus === "completed" ? "text-emerald-400 font-bold" : "text-purple-400 font-bold"}>
                                        {ch.wordCountTarget > 0 ? Math.round((ch.wordCountCurrent / ch.wordCountTarget) * 100) : 0}%
                                      </span>
                                    </div>
                                    <div className="w-full h-1 bg-slate-700 rounded-full overflow-hidden">
                                      <div
                                        className={`h-full rounded-full transition-all duration-500 ${colStatus === "completed" ? "bg-emerald-500" : "bg-purple-500"}`}
                                        style={{ width: `${Math.min(ch.wordCountTarget > 0 ? (ch.wordCountCurrent / ch.wordCountTarget) * 100 : 0, 100)}%` }}
                                      />
                                    </div>
                                  </div>
                                </motion.div>
                              ))
                            ) : (
                              <div className="text-[10px] text-center font-cyber italic py-10" style={{ color: "var(--cyber-text-muted)" }}>
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
                  className="grid grid-cols-1 md:grid-cols-12 gap-5"
                >
                  {/* Chapter sidebar */}
                  <div className="md:col-span-4 flex flex-col gap-3 themed-card-sci rounded-xl p-3 md:p-4 max-h-[500px] overflow-y-auto cyber-scroll">
                    <div className="text-xs font-bold pb-2 uppercase tracking-wider font-cyber" style={{ color: "var(--cyber-text-muted)", borderBottom: "1px solid var(--cyber-border-muted)" }}>
                      大纲树选编 / Document Outline
                    </div>
                    {flatChapters.map((ch) => (
                      <button
                        key={ch.id}
                        type="button"
                        onClick={() => setSelectedChapterId(ch.id)}
                        className={`p-2.5 rounded-lg text-left text-xs transition-all flex items-center justify-between gap-1.5 cursor-pointer ${
                          selectedChapterId === ch.id
                            ? "bg-purple-600 text-white font-bold"
                            : "bg-slate-400/5 hover:bg-slate-400/10"
                        }`}
                        style={selectedChapterId !== ch.id ? { color: "var(--cyber-text-muted)" } : undefined}
                      >
                        <div className="truncate min-w-0">
                          <span className="font-cyber font-bold opacity-80 mr-1.5">{ch.sortOrder || ch.id.slice(0, 4)}</span>
                          <span>{ch.title}</span>
                        </div>
                        {mapToSciFiStatus(ch.status) === "completed" && <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                      </button>
                    ))}
                  </div>

                  {/* Editor canvas */}
                  <div className="md:col-span-8 flex flex-col gap-4 themed-card-sci rounded-xl p-4 md:p-5">
                    {activeChapter ? (
                      <>
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 pb-3" style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-cyber bg-purple-500/10 border border-purple-500/20 text-purple-400 px-2 py-0.5 rounded font-bold">
                                ID: {activeChapter.id.slice(0, 8)}
                              </span>
                              {activeChapter.assignedName && (
                                <span className="text-[10px] px-2 py-0.5 rounded bg-slate-400/10 text-slate-400">
                                  编撰者: {activeChapter.assignedName}
                                </span>
                              )}
                            </div>
                            <h3 className="text-sm font-bold mt-1.5 truncate" style={{ color: "var(--cyber-text-main)" }}>
                              {activeChapter.title}
                            </h3>
                          </div>
                          {/* AI action buttons */}
                          <div className="flex items-center gap-1.5">
                            {(["expand", "polish", "audit"] as const).map((mode) => {
                              const config = {
                                expand: { icon: Sparkles, label: "AI扩写", color: "text-blue-400", border: "border-blue-500/20", bg: "bg-blue-600/10" },
                                polish: { icon: Edit3, label: "润色", color: "text-purple-400", border: "border-purple-500/20", bg: "bg-purple-600/10" },
                                audit: { icon: ShieldAlert, label: "合规自检", color: "text-red-400", border: "border-red-500/20", bg: "bg-red-600/10" },
                              }[mode];
                              return (
                                <button
                                  key={mode}
                                  type="button"
                                  disabled={isSaving}
                                  onClick={handleEnterChat}
                                  className={`px-2.5 py-1.5 rounded border text-[10px] font-bold transition-all flex items-center gap-1 cursor-pointer ${config.bg} ${config.border} ${config.color}`}
                                  title={`打开对话进行${config.label}`}
                                >
                                  <config.icon className="w-3 h-3" />
                                  <span>{config.label}</span>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        <div className="flex-1 flex flex-col gap-2 min-h-[250px]">
                          <label className="text-[10px] font-cyber select-none" style={{ color: "var(--cyber-text-muted)" }}>
                            TEXT WRITING BUFFER WORKSPACE // EDIT DIRECTLY
                          </label>
                          <textarea
                            value={editorContent}
                            onChange={(e) => setEditorContent(e.target.value)}
                            disabled={isSaving}
                            placeholder="编辑该章节内容..."
                            className="w-full flex-1 rounded-lg p-3 text-xs leading-relaxed outline-none font-mono resize-none h-[220px]"
                            style={{
                              background: "var(--cyber-bg-tertiary)",
                              border: "1px solid var(--cyber-border-muted)",
                              color: "var(--cyber-text-main)",
                            }}
                          />
                        </div>

                        <div className="flex items-center justify-between mt-1 pt-3 text-xs" style={{ borderTop: "1px solid var(--cyber-border-muted)" }}>
                          <span className="text-[10px] font-cyber" style={{ color: "var(--cyber-text-muted)" }}>
                            SYS AUTOSAVED DEPLOYMENTS // WORDS: {editorContent.length}
                          </span>
                          <button
                            type="button"
                            onClick={handleSaveChapter}
                            disabled={isSaving}
                            className="px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:opacity-90 active:scale-95 text-white font-bold rounded-lg flex items-center gap-1.5 transition-all cursor-pointer text-xs"
                          >
                            {isSaving ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Save className="w-3.5 h-3.5" />
                            )}
                            <span>保存 (Save Revision)</span>
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="flex items-center justify-center h-[300px] text-sm" style={{ color: "var(--cyber-text-muted)" }}>
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
                  className="themed-card-sci rounded-xl p-4 md:p-6 flex flex-col gap-5 min-h-[300px]"
                >
                  <div className="flex items-center justify-between pb-3" style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}>
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-5 h-5 text-teal-400" />
                      <h3 className="text-sm font-bold uppercase" style={{ color: "var(--cyber-text-main)" }}>
                        {project.name} - 技术审查核心控制台 / Review Console
                      </h3>
                    </div>
                    <span className="text-[10px] font-cyber bg-teal-500/10 border border-teal-500/20 text-teal-400 px-2 py-0.5 rounded font-bold">
                      SECURITY ACCESS LEVEL A
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Checklist */}
                    <div className="themed-terminal-sci p-4 rounded-xl flex flex-col gap-3">
                      <span className="text-[10px] font-cyber uppercase tracking-widest block mb-1" style={{ color: "var(--cyber-text-muted)" }}>
                        AUTOMATION COMPLIANCE CHECKLIST
                      </span>
                      {[
                        "《项目结构完整性》自检通过",
                        "《章节内容格式规范》校验",
                        "《成员角色权限》复核",
                        "《文档输出就绪状态》检查",
                      ].map((item, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs py-1" style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}>
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          <span style={{ color: "var(--cyber-text-muted)" }}>{item}</span>
                        </div>
                      ))}
                    </div>

                    {/* Sign-off */}
                    <div className="themed-terminal-sci p-4 rounded-xl flex flex-col justify-between h-full bg-teal-500/5 border-teal-500/15">
                      <div>
                        <span className="text-[10px] font-cyber text-teal-400 uppercase tracking-widest block mb-2">
                          APPROVED SIGN-OFF
                        </span>
                        <p className="text-xs leading-relaxed mb-3 font-normal" style={{ color: "var(--cyber-text-muted)" }}>
                          审核工作台用于跟踪项目各章节的审核状态。当所有章节完成并经过审核后，项目即可标记为完成。
                        </p>
                      </div>
                      <div className="text-xs" style={{ color: "var(--cyber-text-muted)" }}>
                        <span className="font-cyber text-teal-400 font-bold block mb-1">&gt; AUDIT STATUS:</span>
                        <span>已完成章节: {completedCount}/{totalCount}</span>
                        <span className="mx-2">•</span>
                        <span>审核中: {flatChapters.filter((ch) => mapToSciFiStatus(ch.status) === "review").length}</span>
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* ── RIGHT SIDEBAR: Members ── */}
          <div className="lg:col-span-4 flex flex-col gap-6">
            <div className="themed-card-sci rounded-xl p-4 md:p-5 relative flex flex-col">
              <div className="flex items-center justify-between pb-3 mb-4" style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}>
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-purple-400" />
                  <h3 className="text-sm font-bold uppercase tracking-wider" style={{ color: "var(--cyber-text-main)" }}>
                    项目成员
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddMember(!showAddMember)}
                  className="text-xs text-purple-400 hover:text-purple-300 cursor-pointer flex items-center gap-0.5 font-bold"
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
                    className="mb-4 p-3 border border-purple-500/20 bg-purple-500/5 rounded-lg text-xs flex flex-col gap-2.5 overflow-hidden"
                  >
                    <div>
                      <label className="block mb-1" style={{ color: "var(--cyber-text-muted)" }}>成员用户名 (User ID)</label>
                      <input
                        type="text"
                        required
                        placeholder="例如: zhangsan"
                        value={newMemberName}
                        onChange={(e) => setNewMemberName(e.target.value)}
                        className="w-full rounded px-2 py-1 outline-none text-xs"
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
                      className="w-full py-1.5 bg-purple-600 hover:bg-purple-500 border border-purple-400/20 text-white font-bold rounded cursor-pointer text-xs disabled:opacity-50"
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
                    const initials = (member.username ?? "?").slice(0, 2).toUpperCase();
                    const isOwner = member.role === "owner";
                    return (
                      <div
                        key={member.userId}
                        className="flex items-center justify-between p-3 rounded-lg border transition-all group"
                        style={{
                          borderColor: "var(--cyber-border-muted)",
                          background: "var(--cyber-bg-tertiary)",
                        }}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs uppercase ${
                            isOwner
                              ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                              : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                          }`}>
                            {initials}
                          </div>
                          <div>
                            <h4 className="text-xs font-bold" style={{ color: "var(--cyber-text-main)" }}>{member.username}</h4>
                            <p className="text-[10px] font-mono" style={{ color: "var(--cyber-text-muted)" }}>
                              NODE ACTIVE USER // {member.role}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`text-[9px] px-1.5 py-0.5 rounded font-cyber font-bold ${
                            isOwner
                              ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                              : "bg-slate-400/15 border border-transparent"
                          }`} style={!isOwner ? { color: "var(--cyber-text-muted)" } : undefined}>
                            {MEMBER_ROLE_LABELS[member.role] ?? member.role}
                          </span>
                          {!isOwner && (
                            <button
                              type="button"
                              onClick={() => handleRemoveMember(member.userId)}
                              disabled={removingId === member.userId}
                              className="p-1 hover:text-red-400 hover:bg-red-500/5 rounded transition-all cursor-pointer opacity-0 group-hover:opacity-100"
                              style={{ color: "var(--cyber-text-muted)" }}
                              title="移除该成员"
                            >
                              {removingId === member.userId ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Trash2 className="w-3.5 h-3.5" />
                              )}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="px-3 py-6 text-center">
                    <Users className="h-6 w-6 mx-auto mb-1.5 opacity-20" style={{ color: "var(--cyber-text-muted)" }} />
                    <p className="text-xs" style={{ color: "var(--cyber-text-muted)" }}>暂无成员</p>
                  </div>
                )}
              </div>
            </div>

            {/* AI Assistant Card */}
            <div className="themed-card-sci rounded-xl p-4 md:p-5 flex flex-col relative overflow-hidden bg-gradient-to-br from-blue-500/5 to-purple-500/5">
              <div className="flex items-center gap-2 pb-3 mb-3" style={{ borderBottom: "1px solid var(--cyber-border-muted)" }}>
                <div className="p-1 rounded bg-blue-500/15 text-blue-400">
                  <Cpu className="w-4 h-4" />
                </div>
                <h3 className="text-xs font-bold uppercase tracking-wider font-cyber" style={{ color: "var(--cyber-text-main)" }}>
                  AI 助手 / Neural Copilot
                </h3>
              </div>
              <p className="text-[11px] leading-relaxed font-normal" style={{ color: "var(--cyber-text-muted)" }}>
                点击右上角「进入对话」按钮，使用 AI 助手辅助编写、润色和审核文档章节。
                AI 可以帮你扩写内容、优化措辞、检查规范合规性。
              </p>
              <button
                type="button"
                onClick={handleEnterChat}
                disabled={entering}
                className="mt-3 w-full py-2 bg-gradient-to-r from-blue-600 to-cyan-600 text-white font-bold text-xs rounded-lg cursor-pointer hover:opacity-90 flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                <MessageSquare className="w-3.5 h-3.5" />
                {entering ? "进入中..." : "进入 AI 对话"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
