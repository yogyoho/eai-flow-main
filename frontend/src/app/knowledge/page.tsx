"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Clock,
  Database,
  Edit,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Trash2,
  X,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import React, { Suspense, useEffect, useState } from "react";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
// EAI-CUSTOM: button-level permission control
import { PermissionProvider, usePermission } from "@/core/permissions";
import { kbApi } from "@/extensions/api";
import type {
  CreateKnowledgeBaseRequest,
  KnowledgeBase,
  UpdateKnowledgeBaseRequest,
} from "@/extensions/types";
import { cn } from "@/lib/utils";

import { CustomSelect } from "./_components/CustomSelect";
import { ToastContainer, useToast } from "./_components/toast";

// ─── helpers ────────────────────────────────────────────────────────────────

const KB_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "ragflow", label: "RAGFlow" },
  { value: "pageindex", label: "PageIndex" },
];

const CHUNK_METHOD_OPTIONS: { value: string; label: string }[] = [
  { value: "naive", label: "通用 (General)" },
  { value: "qa", label: "问答 (Q&A)" },
  { value: "manual", label: "手册 (Manual)" },
  { value: "table", label: "表格 (Table)" },
  { value: "paper", label: "论文 (Paper)" },
  { value: "book", label: "书籍 (Book)" },
  { value: "laws", label: "法律 (Laws)" },
  { value: "presentation", label: "演示文稿 (Presentation)" },
  { value: "picture", label: "图片 (Picture)" },
  { value: "one", label: "整篇 (One)" },
  { value: "tag", label: "标签集 (Tag)" },
];

const LAYOUT_RECOGNIZE_OPTIONS: { value: string; label: string; desc: string }[] = [
  { value: "DeepDOC", label: "DeepDOC (默认)", desc: "OCR + TSR + DLR，默认视觉模型，准确但较慢" },
  { value: "Naive", label: "快速解析 (Naive)", desc: "跳过 OCR/TSR/DLR，仅适用于纯文本 PDF" },
  { value: "MinerU", label: "MinerU", desc: "开源 PDF 转换工具，将 PDF 转为机器可读格式" },
  { value: "Docling", label: "Docling", desc: "开源文档处理工具，为生成式 AI 优化" },
  { value: "OpenDataLoader", label: "OpenDataLoader", desc: "确定性本地 PDF 解析器，输出 JSON + Markdown" },
];

function knowledgeBaseTypeLabel(kbType: string | undefined): string {
  if (!kbType) return "RAGFlow";
  return KB_TYPE_OPTIONS.find((o) => o.value === kbType)?.label ?? kbType;
}

// ─── KnowledgeBaseManagement ─────────────────────────────────────────────────

function KnowledgeBaseManagement({ initialSearch = "" }: { initialSearch?: string }) {
  // EAI-CUSTOM: button-level permission check
  const { can } = usePermission();
  const { toasts, show: toast, remove } = useToast();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState(initialSearch);
  const [typeFilter, setTypeFilter] = useState("all");
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());

  // Create modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<CreateKnowledgeBaseRequest>({
    name: "",
    description: "",
    access_type: "private",
    kb_type: "ragflow",
    chunk_method: "naive",
    embedding_model: undefined,
    parser_config: {
      chunk_token_num: 512,
      delimiter: "\\n",
      layout_recognize: "DeepDOC",
    },
    language: "Chinese",
  });

  // Embedding models for RAGFlow
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([]);
  const [embeddingModelsLoading, setEmbeddingModelsLoading] = useState(false);
  const [embeddingModelsError, setEmbeddingModelsError] = useState(false);

  // Fetch embedding models when create dialog opens and kb_type is ragflow
  useEffect(() => {
    if (!isCreateOpen || createForm.kb_type !== "ragflow") return;
    let cancelled = false;
    setEmbeddingModelsLoading(true);
    setEmbeddingModelsError(false);
    kbApi.listEmbeddingModels().then((res) => {
      if (cancelled) return;
      setEmbeddingModels(res.models || []);
      setEmbeddingModelsLoading(false);
      if (!res.models?.length && res.error) {
        setEmbeddingModelsError(true);
      }
    }).catch(() => {
      if (cancelled) return;
      setEmbeddingModels([]);
      setEmbeddingModelsLoading(false);
      setEmbeddingModelsError(true);
    });
    return () => { cancelled = true; };
  }, [isCreateOpen, createForm.kb_type]);

  // Edit modal
  const [editKb, setEditKb] = useState<KnowledgeBase | null>(null);
  const [editForm, setEditForm] = useState<UpdateKnowledgeBaseRequest>({});
  const [editLoading, setEditLoading] = useState(false);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const res = await kbApi.list({ limit: 500 });
      setKbs(res.knowledge_bases);
    } catch (e: any) {
      toast(e?.message ?? "加载失败", "error");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredKBs = kbs.filter((kb) => {
    const matchesSearch =
      kb.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (kb.description ?? "").toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType =
      typeFilter === "all" || (kb.kb_type ?? "ragflow") === typeFilter;
    return matchesSearch && matchesType;
  });

  const handleCreate = async () => {
    if (!createForm.name.trim()) return;
    try {
      const kb = await kbApi.create(createForm);
      setKbs((prev) => [kb, ...prev]);
      setIsCreateOpen(false);
      setCreateForm({
        name: "",
        description: "",
        access_type: "private",
        kb_type: "ragflow",
        chunk_method: "naive",
        embedding_model: undefined,
        parser_config: {
          chunk_token_num: 512,
          delimiter: "\\n",
          layout_recognize: "DeepDOC",
        },
        language: "Chinese",
      });
      toast("知识库创建成功", "success");
    } catch (e: any) {
      toast(e?.message ?? "创建失败", "error");
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定要删除该知识库吗？")) return;
    try {
      await kbApi.delete(id);
      setKbs((prev) => prev.filter((kb) => kb.id !== id));
      toast("知识库已删除", "success");
    } catch (e: any) {
      toast(e?.message ?? "删除失败", "error");
    }
  };

  const handleSync = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSyncingIds((prev) => new Set(prev).add(id));
    try {
      const status = await kbApi.getStatus(id);
      setKbs((prev) =>
        prev.map((kb) =>
          kb.id === id ? { ...kb, status: status.status } : kb,
        ),
      );
      toast("同步状态已刷新", "success");
    } catch (e: any) {
      toast(e?.message ?? "同步失败", "error");
    } finally {
      setSyncingIds((prev) => {
        const s = new Set(prev);
        s.delete(id);
        return s;
      });
    }
  };

  const openEdit = (kb: KnowledgeBase, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditKb(kb);
    setEditForm({
      name: kb.name,
      description: kb.description ?? "",
      access_type: kb.access_type,
      kb_type: kb.kb_type ?? "ragflow",
    });
  };

  const handleEditSave = async () => {
    if (!editKb) return;
    setEditLoading(true);
    try {
      const updated = await kbApi.update(editKb.id, editForm);
      setKbs((prev) => prev.map((kb) => (kb.id === editKb.id ? updated : kb)));
      setEditKb(null);
      toast("知识库信息已更新", "success");
    } catch (e: any) {
      toast(e?.message ?? "更新失败", "error");
    } finally {
      setEditLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const base = "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium";
    if (status === "active" || status === "done")
      return (
        <span className={cn(base, "border border-success/20 bg-success/10 text-success")}>
          <CheckCircle2 className="h-3 w-3" />
          已就绪
        </span>
      );
    if (status === "syncing" || status === "processing")
      return (
        <span className={cn(base, "border border-primary/20 bg-primary/10 text-primary")}>
          <RefreshCw className="h-3 w-3 animate-spin" />
          同步中
        </span>
      );
    if (status === "error" || status === "failed")
      return (
        <span className={cn(base, "border border-destructive/20 bg-destructive/10 text-destructive")}>
          <AlertCircle className="h-3 w-3" />
          同步失败
        </span>
      );
    return (
      <span className={cn(base, "border border-border bg-muted text-muted-foreground")}>
        <Clock className="h-3 w-3" />
        未同步
      </span>
    );
  };

  return (
    <main className="flex-1 overflow-y-auto bg-muted/50 p-8">
      <div className="mx-auto max-w-6xl space-y-8">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-3 border rounded-lg bg-blue-50 border-blue-200 text-blue-600 shrink-0">
              <BookOpen className="w-6 h-6" />
            </div>
            <div className="min-w-0">
              <h1 className="text-2xl font-bold tracking-tight text-foreground">知识库管理</h1>
              <p className="text-sm text-muted-foreground mt-1">
                管理 RAGFlow 知识库，上传文档并监控同步状态。
              </p>
            </div>
          </div>
          {/* EAI-CUSTOM: gate create button by kb:create permission */}
          {can("kb:create") && (
            <Button onClick={() => setIsCreateOpen(true)} className="shrink-0">
              <Plus className="h-4 w-4" />
              新建知识库
            </Button>
          )}
        </div>

        {/* Filters */}
        <div className="flex flex-col items-center justify-between gap-4 rounded-xl border border-border bg-background p-4 shadow-sm sm:flex-row">
          <div className="relative w-full sm:w-64">
            <Search className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              placeholder="搜索知识库名称或描述..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-muted pl-9 pr-4"
            />
          </div>
          <div className="w-full sm:w-48">
            <CustomSelect
              value={typeFilter}
              onChange={setTypeFilter}
              options={[
                {
                  value: "all",
                  label: "所有类型",
                  icon: <Search className="h-3.5 w-3.5" />,
                },
                {
                  value: "ragflow",
                  label: "RAGFlow",
                  icon: <Database className="h-3.5 w-3.5" />,
                },
                {
                  value: "pageindex",
                  label: "PageIndex",
                  icon: <FileText className="h-3.5 w-3.5" />,
                },
              ]}
            />
          </div>
        </div>

        {/* Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-center text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            加载中...
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence>
              {filteredKBs.map((kb) => {
                const kbType = kb.kb_type ?? "ragflow";
                const isSyncing = syncingIds.has(kb.id);
                return (
                  <motion.div
                    layout
                    key={kb.id}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ duration: 0.2 }}
                    onClick={() => router.push(`/knowledge/${kb.id}`)}
                    className="group flex cursor-pointer flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md"
                  >
                    <div className="flex-1 p-5">
                      <div className="mb-4 flex items-center gap-3">
                        <div
                          className={cn(
                            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border",
                            kbType === "ragflow"
                              ? "border-primary/20 bg-primary/10 text-primary"
                              : "border-success/20 bg-success/10 text-success",
                          )}
                        >
                          {kbType === "ragflow" ? (
                            <Database className="h-5 w-5" />
                          ) : (
                            <FileText className="h-5 w-5" />
                          )}
                        </div>
                        <div className="min-w-0">
                          <h3 className="line-clamp-1 font-semibold text-foreground">
                            {kb.name}
                          </h3>
                          <div className="mt-0.5 flex items-center gap-1.5">
                            <span
                              className={cn(
                                "inline-block rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                                kbType === "ragflow"
                                  ? "bg-primary/10 text-primary"
                                  : "bg-success/10 text-success",
                              )}
                            >
                              {knowledgeBaseTypeLabel(kbType)}
                            </span>
                            {getStatusBadge(kb.status)}
                          </div>
                        </div>
                      </div>

                      <p className="mb-4 line-clamp-2 h-10 text-sm text-muted-foreground">
                        {kb.description || "暂无描述"}
                      </p>

                      <div className="grid grid-cols-3 gap-3 border-t border-border py-3">
                        <div>
                          <div className="mb-1 text-xs text-muted-foreground">
                            知识库类型
                          </div>
                          <div
                            className="truncate text-sm font-medium text-foreground"
                            title={knowledgeBaseTypeLabel(kbType)}
                          >
                            {knowledgeBaseTypeLabel(kbType)}
                          </div>
                        </div>
                        <div>
                          <div className="mb-1 text-xs text-muted-foreground">
                            创建时间
                          </div>
                          <div className="text-sm font-medium text-foreground">
                            {new Date(kb.created_at).toLocaleDateString(
                              "zh-CN",
                            )}
                          </div>
                        </div>
                        <div>
                          <div className="mb-1 text-xs text-muted-foreground">
                            分块方式
                          </div>
                          <div className="truncate text-sm font-medium text-foreground">
                            {kb.chunk_method || "naive"}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between border-t border-border bg-muted/50 px-5 py-3">
                      <div className="text-xs text-muted-foreground">
                        {kb.owner_name || "未知"}
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => handleSync(kb.id, e)}
                          disabled={isSyncing}
                          className="text-muted-foreground hover:bg-primary/10 hover:text-primary"
                          title="同步状态"
                        >
                          <RefreshCw
                            className={cn(
                              "h-4 w-4",
                              isSyncing && "animate-spin",
                            )}
                          />
                        </Button>
                        {/* EAI-CUSTOM: gate KB edit button by kb:update permission */}
                        {can("kb:update") && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={(e) => openEdit(kb, e)}
                            className="text-muted-foreground hover:bg-muted hover:text-foreground"
                            title="编辑"
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                        )}
                        {/* EAI-CUSTOM: gate KB-delete button by kb:delete permission */}
                        {can("kb:delete") && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={(e) => handleDelete(kb.id, e)}
                            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                            title="删除"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>

            {filteredKBs.length === 0 && (
              <div className="col-span-full rounded-xl border border-dashed border-border bg-background py-12 text-center">
                <Database className="mx-auto mb-3 h-12 w-12 text-muted-foreground/50" />
                <h3 className="text-sm font-medium text-foreground">
                  未找到知识库
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  尝试调整搜索词或筛选条件
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create Modal */}
      <AnimatePresence>
        {isCreateOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setIsCreateOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-background shadow-xl"
            >
              <div className="flex shrink-0 items-center gap-3 border-b border-border bg-muted/50 px-6 py-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
                  <Database className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-lg leading-tight font-semibold text-foreground">
                    新建知识库
                  </h3>
                  <div className="text-xs text-muted-foreground">
                    创建一个新的文档知识库
                  </div>
                </div>
              </div>
              <div className="flex-1 space-y-5 overflow-y-auto p-6">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库名称 <span className="text-destructive">*</span>
                  </label>
                  <Input
                    type="text"
                    value={createForm.name}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, name: e.target.value })
                    }
                    className="w-full"
                    placeholder="例如：产品操作手册"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    访问权限
                  </label>
                  <CustomSelect
                    value={createForm.access_type ?? "private"}
                    onChange={(v) =>
                      setCreateForm({ ...createForm, access_type: v })
                    }
                    options={[
                      {
                        value: "private",
                        label: "私有",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center text-xs">
                            🔒
                          </span>
                        ),
                      },
                      {
                        value: "public",
                        label: "公开",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center justify-center">
                            🌐
                          </span>
                        ),
                      },
                      {
                        value: "dept",
                        label: "部门可见",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center justify-center">
                            🏢
                          </span>
                        ),
                      },
                    ]}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库类型
                  </label>
                  <CustomSelect
                    value={createForm.kb_type ?? "ragflow"}
                    onChange={(v) =>
                      setCreateForm({ ...createForm, kb_type: v })
                    }
                    options={KB_TYPE_OPTIONS.map((o) => ({
                      value: o.value,
                      label: o.label,
                      icon:
                        o.value === "ragflow" ? (
                          <Database className="h-3.5 w-3.5" />
                        ) : (
                          <FileText className="h-3.5 w-3.5" />
                        ),
                    }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    描述
                  </label>
                  <Textarea
                    value={createForm.description ?? ""}
                    rows={3}
                    onChange={(e) =>
                      setCreateForm({
                        ...createForm,
                        description: e.target.value,
                      })
                    }
                    className="w-full resize-none"
                    placeholder="简要描述该知识库的用途或包含的内容..."
                  />
                </div>

                {/* RAGFlow Parameters — conditional */}
                {createForm.kb_type === "ragflow" && (
                  <div className="space-y-4 rounded-xl border border-primary/20 bg-primary/5 p-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <Settings className="h-4 w-4 text-primary" />
                      RAGFlow 参数
                    </div>

                    {/* Language */}
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground">
                        语言
                      </label>
                      <CustomSelect
                        value={createForm.language ?? "Chinese"}
                        onChange={(v) =>
                          setCreateForm({ ...createForm, language: v })
                        }
                        options={[
                          { value: "Chinese", label: "中文" },
                          { value: "English", label: "English" },
                        ]}
                      />
                    </div>

                    {/* Chunk Method */}
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground">
                        分块方式
                      </label>
                      <CustomSelect
                        value={createForm.chunk_method ?? "naive"}
                        onChange={(v) =>
                          setCreateForm({ ...createForm, chunk_method: v })
                        }
                        options={CHUNK_METHOD_OPTIONS.map((o) => ({
                          value: o.value,
                          label: o.label,
                        }))}
                      />
                    </div>

                    {/* Embedding Model */}
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground">
                        嵌入模型
                      </label>
                      {embeddingModelsLoading ? (
                        <div className="flex items-center gap-2 rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-muted-foreground">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          加载模型列表...
                        </div>
                      ) : embeddingModelsError || embeddingModels.length === 0 ? (
                        <Input
                          type="text"
                          value={createForm.embedding_model ?? ""}
                          onChange={(e) =>
                            setCreateForm({ ...createForm, embedding_model: e.target.value || undefined })
                          }
                          className="w-full"
                          placeholder="model_name@factory（例如：BAAI/bge-large-zh-v1.5@BAAI）"
                        />
                      ) : (
                        <CustomSelect
                          value={createForm.embedding_model ?? embeddingModels[0] ?? ""}
                          onChange={(v) =>
                            setCreateForm({ ...createForm, embedding_model: v })
                          }
                          options={embeddingModels.map((m) => ({
                            value: m,
                            label: m,
                          }))}
                        />
                      )}
                      {embeddingModelsError && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          无法获取模型列表，请手动输入 model_name@factory 格式
                        </p>
                      )}
                    </div>

                    {/* Chunk Size (chunk_token_num) */}
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground">
                        分块大小{" "}
                        <span className="font-normal text-muted-foreground">
                          （token 数量）
                        </span>
                      </label>
                      <div className="flex items-center gap-3">
                        <input
                          type="range"
                          min={128}
                          max={2048}
                          step={128}
                          value={createForm.parser_config?.chunk_token_num ?? 512}
                          onChange={(e) =>
                            setCreateForm({
                              ...createForm,
                              parser_config: {
                                ...createForm.parser_config,
                                chunk_token_num: Number(e.target.value),
                              },
                            })
                          }
                          className="flex-1 accent-primary"
                        />
                        <span className="w-12 text-center text-sm font-medium text-foreground">
                          {createForm.parser_config?.chunk_token_num ?? 512}
                        </span>
                      </div>
                    </div>

                    {/* Delimiter */}
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground">
                        分隔符
                      </label>
                      <Input
                        type="text"
                        value={createForm.parser_config?.delimiter ?? "\\n"}
                        onChange={(e) =>
                          setCreateForm({
                            ...createForm,
                            parser_config: {
                              ...createForm.parser_config,
                              delimiter: e.target.value,
                            },
                          })
                        }
                        className="w-full"
                        placeholder="\\n"
                      />
                    </div>

                    {/* PDF Parser (layout_recognize) */}
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground">
                        PDF 解析方式
                      </label>
                      <CustomSelect
                        value={createForm.parser_config?.layout_recognize ?? "DeepDOC"}
                        onChange={(v) =>
                          setCreateForm({
                            ...createForm,
                            parser_config: {
                              ...createForm.parser_config,
                              layout_recognize: v,
                            },
                          })
                        }
                        options={LAYOUT_RECOGNIZE_OPTIONS.map((o) => ({
                          value: o.value,
                          label: o.label,
                          desc: o.desc,
                        }))}
                      />
                    </div>
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
                <Button
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={!createForm.name.trim()}
                >
                  创建
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Edit Modal */}
      <AnimatePresence>
        {editKb && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setEditKb(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-background shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-border px-6 py-4">
                <h3 className="text-lg font-semibold text-foreground">
                  编辑知识库
                </h3>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setEditKb(null)}
                >
                  <X className="h-5 w-5" />
                </Button>
              </div>
              <div className="space-y-5 p-6">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库名称 <span className="text-destructive">*</span>
                  </label>
                  <Input
                    type="text"
                    value={editForm.name ?? ""}
                    onChange={(e) =>
                      setEditForm({ ...editForm, name: e.target.value })
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    访问权限
                  </label>
                  <CustomSelect
                    value={editForm.access_type ?? "private"}
                    onChange={(v) =>
                      setEditForm({ ...editForm, access_type: v })
                    }
                    options={[
                      {
                        value: "private",
                        label: "私有",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center text-xs">
                            🔒
                          </span>
                        ),
                      },
                      {
                        value: "public",
                        label: "公开",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center justify-center">
                            🌐
                          </span>
                        ),
                      },
                      {
                        value: "dept",
                        label: "部门可见",
                        icon: (
                          <span className="flex h-3.5 w-3.5 items-center justify-center">
                            🏢
                          </span>
                        ),
                      },
                    ]}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    知识库类型
                  </label>
                  <CustomSelect
                    value={editForm.kb_type ?? "ragflow"}
                    onChange={(v) => setEditForm({ ...editForm, kb_type: v })}
                    options={KB_TYPE_OPTIONS.map((o) => ({
                      value: o.value,
                      label: o.label,
                      icon:
                        o.value === "ragflow" ? (
                          <Database className="h-3.5 w-3.5" />
                        ) : (
                          <FileText className="h-3.5 w-3.5" />
                        ),
                    }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    描述
                  </label>
                  <Textarea
                    value={editForm.description ?? ""}
                    rows={3}
                    onChange={(e) =>
                      setEditForm({ ...editForm, description: e.target.value })
                    }
                    className="w-full resize-none"
                  />
                </div>
              </div>
              <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
                <Button
                  variant="outline"
                  onClick={() => setEditKb(null)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleEditSave}
                  disabled={!editForm.name?.trim() || editLoading}
                >
                  {editLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                  保存
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <ToastContainer toasts={toasts} onRemove={remove} />
    </main>
  );
}

// ─── Page export ─────────────────────────────────────────────────────────────

function KnowledgePageInner() {
  const searchParams = useSearchParams();
  const initialSearch = searchParams.get("search") || "";
  return <KnowledgeBaseManagement initialSearch={initialSearch} />;
}

export default function KnowledgePage() {
  return (
    <PermissionProvider>
      <SimpleShellLayout>
        <Suspense fallback={<div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>}>
          <KnowledgePageInner />
        </Suspense>
      </SimpleShellLayout>
    </PermissionProvider>
  );
}
