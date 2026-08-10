"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRightToLine,
  CheckCircle2,
  ChevronLeft,
  Copy,
  Database,
  Edit3,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Search as SearchIcon,
  Settings,
  Trash2,
  X,
} from "lucide-react";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { usePermission } from "@/core/permissions";
import { deptApi, kbApi, roleApi, userApi } from "@/extensions/api";
import type {
  Department,
  Document,
  KnowledgeBase,
  KnowledgeBaseGrant,
  RAGChatResponse,
  Role,
  UpdateKnowledgeBaseRequest,
  User,
} from "@/extensions/types";
import { cn } from "@/lib/utils";

import { ChunkModal } from "./ChunkModal";
import { CustomSelect } from "./CustomSelect";
import { DocStatusBadge } from "./DocStatusBadge";
import { sortSourcesByScore } from "./sources-sort";
import { ToastContainer, useToast } from "./toast";
import { UploadModal, formatFileSize } from "./UploadModal";

function formatDate(dateString: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateString));
}

const KB_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "ragflow", label: "RAGFlow" },
  { value: "pageindex", label: "PageIndex" },
];

function knowledgeBaseTypeLabel(kbType: string | undefined): string {
  if (!kbType) return "RAGFlow";
  return KB_TYPE_OPTIONS.find((o) => o.value === kbType)?.label ?? kbType;
}

export function KnowledgeBaseDetail({
  kb,
  onBack,
  onKbUpdated,
}: {
  kb: KnowledgeBase;
  onBack: () => void;
  onKbUpdated?: (kb: KnowledgeBase) => void;
}) {
  const { toasts, show: toast, remove } = useToast();

  // EAI-CUSTOM: button-level permission check for upload/delete actions
  const { can, is_admin, identity } = usePermission();
  const [isFormatted, setIsFormatted] = useState(false);
  const [query, setQuery] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatResult, setChatResult] = useState<{ answer?: string; sources?: RAGChatResponse["sources"] } | null>(null);
  const [previewChunk, setPreviewChunk] = useState<{ content: string; name?: string } | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [fileSearch, setFileSearch] = useState("");
  const [showUpload, setShowUpload] = useState(false);
  const [showEditKb, setShowEditKb] = useState(false);
  const [showChunksDoc, setShowChunksDoc] = useState<Document | null>(null);
  const [editForm, setEditForm] = useState<UpdateKnowledgeBaseRequest>({
    name: kb.name,
    description: kb.description ?? "",
    kb_type: kb.kb_type ?? "ragflow",
  });
  const [editLoading, setEditLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Data access grants (EAI-CUSTOM Task 8) ──────────────────────────────────
  const canManageGrants = is_admin || kb.owner_id === identity.user_id;
  const [kbGrants, setKbGrants] = useState<KnowledgeBaseGrant[]>([]);
  const [grantUsers, setGrantUsers] = useState<User[]>([]);
  const [grantDepts, setGrantDepts] = useState<Department[]>([]);
  const [grantRoles, setGrantRoles] = useState<Role[]>([]);
  const [showAddGrant, setShowAddGrant] = useState(false);
  const [grantType, setGrantType] = useState<"user" | "dept" | "role">("user");
  const [grantTargetId, setGrantTargetId] = useState("");
  const [grantSearch, setGrantSearch] = useState("");
  const [grantPermission, setGrantPermission] = useState<"read" | "write">("read");
  const [grantExpires, setGrantExpires] = useState("");
  const [grantSaving, setGrantSaving] = useState(false);

  const loadGrants = useCallback(async () => {
    try {
      setKbGrants(await kbApi.grants.list(kb.id));
    } catch {
      setKbGrants([]);
    }
  }, [kb.id]);

  const loadGrantTargets = useCallback(async () => {
    try {
      const [u, d, r] = await Promise.all([
        userApi.list({ limit: 500 }),
        deptApi.list({ limit: 500 }),
        roleApi.list({ limit: 500 }),
      ]);
      setGrantUsers(u.users);
      setGrantDepts(d.departments);
      setGrantRoles(r.roles);
    } catch {
      // granteeName degrades to raw ids when lookups fail
    }
  }, []);

  useEffect(() => {
    if (!canManageGrants) return;
    void loadGrants();
    void loadGrantTargets();
  }, [canManageGrants, loadGrants, loadGrantTargets]);

  const granteeName = useCallback(
    (g: KnowledgeBaseGrant) => {
      if (g.grantee_type === "user") {
        const u = grantUsers.find((x) => x.id === g.grantee_id);
        return u?.full_name || u?.username || g.grantee_id;
      }
      if (g.grantee_type === "dept") {
        const d = grantDepts.find((x) => x.id === g.grantee_id);
        return d?.name || d?.code || g.grantee_id;
      }
      const r = grantRoles.find((x) => x.id === g.grantee_id);
      return r?.name || r?.code || g.grantee_id;
    },
    [grantUsers, grantDepts, grantRoles],
  );

  const openAddGrant = () => {
    setGrantType("user");
    setGrantTargetId("");
    setGrantSearch("");
    setGrantPermission("read");
    setGrantExpires("");
    setShowAddGrant(true);
  };

  const handleGrantTypeChange = (t: string) => {
    setGrantType(t as "user" | "dept" | "role");
    setGrantTargetId("");
    setGrantSearch("");
  };

  const grantTargets = useMemo(() => {
    const q = grantSearch.trim().toLowerCase();
    if (grantType === "user") {
      return grantUsers
        .filter(
          (u) =>
            !q ||
            u.username.toLowerCase().includes(q) ||
            (u.full_name ?? "").toLowerCase().includes(q),
        )
        .map((u) => ({ id: u.id, label: u.full_name || u.username || u.id }));
    }
    if (grantType === "dept") {
      return grantDepts
        .filter(
          (d) =>
            !q ||
            d.name.toLowerCase().includes(q) ||
            (d.code ?? "").toLowerCase().includes(q),
        )
        .map((d) => ({ id: d.id, label: d.name || d.code || d.id }));
    }
    return grantRoles
      .filter(
        (r) =>
          !q ||
          r.name.toLowerCase().includes(q) ||
          r.code.toLowerCase().includes(q),
      )
      .map((r) => ({ id: r.id, label: r.name || r.code }));
  }, [grantType, grantSearch, grantUsers, grantDepts, grantRoles]);

  const handleAddGrant = async () => {
    if (!grantTargetId) {
      toast("请选择要授权的对象", "error");
      return;
    }
    setGrantSaving(true);
    try {
      await kbApi.grants.create(kb.id, {
        grantee_type: grantType,
        grantee_id: grantTargetId,
        permission: grantPermission,
        expires_at: grantExpires ? new Date(grantExpires).toISOString() : null,
      });
      toast("授权已添加", "success");
      setShowAddGrant(false);
      void loadGrants();
    } catch (e: any) {
      toast(e?.message ?? "添加授权失败", "error");
    } finally {
      setGrantSaving(false);
    }
  };

  const removeGrant = async (g: KnowledgeBaseGrant) => {
    if (!confirm(`确定要移除「${granteeName(g)}」的访问授权吗？`)) return;
    try {
      await kbApi.grants.remove(g.kb_id, g.id);
      setKbGrants((prev) => prev.filter((x) => x.id !== g.id));
      toast("授权已移除", "success");
    } catch (e: any) {
      toast(e?.message ?? "移除授权失败", "error");
    }
  };

  useEffect(() => {
    setEditForm({
      name: kb.name,
      description: kb.description ?? "",
      kb_type: kb.kb_type ?? "ragflow",
    });
  }, [kb.id, kb.name, kb.description, kb.kb_type]);

  // Config tab state
  const [topK, setTopK] = useState(kb.retrieval_config?.top_k ?? 5);
  const [similarityThreshold, setSimilarityThreshold] = useState(
    kb.retrieval_config?.similarity_threshold ?? 0.2,
  );
  const [vectorWeight, setVectorWeight] = useState(
    kb.retrieval_config?.vector_similarity_weight ?? 0.3,
  );
  const [configSaving, setConfigSaving] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);
  const markDirty = () => setConfigDirty(true);

  const loadDocs = useCallback(async () => {
    try {
      const res = await kbApi.listDocs(kb.id, { limit: 200 });
      setDocs(res.documents);
      return res.documents;
    } catch (e: any) {
      toast(e?.message ?? "加载文档失败", "error");
      return [];
    } finally {
      setDocsLoading(false);
    }
  }, [kb.id, toast]);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  // Poll while any doc is in processing state
  useEffect(() => {
    const hasProcessing = docs.some((d) =>
      ["uploading", "processing", "pending"].includes(d.status),
    );
    if (hasProcessing && !pollRef.current) {
      pollRef.current = setInterval(loadDocs, 3000);
    } else if (!hasProcessing && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [docs, loadDocs]);

  const handleDeleteDoc = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定要删除该文件吗？")) return;
    try {
      await kbApi.deleteDoc(kb.id, docId);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
      toast("文件已删除", "success");
    } catch (e: any) {
      toast(e?.message ?? "删除失败", "error");
    }
  };

  const handleSearch = async () => {
    if (!query.trim()) return;
    setChatLoading(true);
    setChatResult(null);
    try {
      const result = await kbApi.chat(kb.id, {
        query,
        top_k: topK,
        // similarity_threshold / vector_similarity_weight omitted → backend falls back to persisted retrieval_config
      });
      setChatResult({
        answer: result.answer,
        sources: sortSourcesByScore(result.sources),
      });
    } catch (e) {
      toast((e as { message?: string })?.message ?? "检索失败", "error");
    } finally {
      setChatLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    setConfigSaving(true);
    try {
      const updated = await kbApi.updateRetrievalConfig(kb.id, {
        top_k: topK,
        similarity_threshold: similarityThreshold,
        vector_similarity_weight: vectorWeight,
      });
      onKbUpdated?.(updated);
      setConfigDirty(false);
      toast("检索配置已保存", "success");
    } catch (e) {
      toast((e as { message?: string })?.message ?? "保存失败", "error");
    } finally {
      setConfigSaving(false);
    }
  };

  const handleResetConfig = () => {
    setTopK(kb.retrieval_config?.top_k ?? 5);
    setSimilarityThreshold(kb.retrieval_config?.similarity_threshold ?? 0.2);
    setVectorWeight(kb.retrieval_config?.vector_similarity_weight ?? 0.3);
    setConfigDirty(false);
  };

  const handleEditSave = async () => {
    setEditLoading(true);
    try {
      const updated = await kbApi.update(kb.id, editForm);
      onKbUpdated?.(updated);
      toast("知识库信息已更新", "success");
      setShowEditKb(false);
    } catch (e: any) {
      toast(e?.message ?? "更新失败", "error");
    } finally {
      setEditLoading(false);
    }
  };

  const filteredDocs = docs.filter((d) =>
    d.name.toLowerCase().includes(fileSearch.toLowerCase()),
  );

  return (
    <div className="flex h-full gap-4 overflow-hidden p-6">
      {/* Left Pane */}
      <div className="flex w-1/2 flex-col gap-4 overflow-hidden">
        {/* Header Card */}
        <div className="shrink-0 rounded-xl border border-border bg-background p-6">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                onClick={onBack}
              >
                <ChevronLeft className="h-5 w-5" />
              </Button>
              <h2 className="text-lg font-semibold text-foreground">{kb.name}</h2>
              <span className="rounded bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">
                ID: {kb.id}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={() =>
                  navigator.clipboard
                    .writeText(kb.id)
                    .then(() => toast("ID 已复制", "success"))
                }
                title="复制 ID"
              >
                <Copy className="h-4 w-4" />
              </Button>
              {/* EAI-CUSTOM: gate KB edit trigger by kb:update permission */}
              {can("kb:update") && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowEditKb(true)}
                  title="编辑"
                >
                  <Edit3 className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            {kb.description || "暂无描述"}
          </p>
        </div>

        {/* File List Card */}
        <div className="flex flex-1 flex-col overflow-hidden rounded-xl border border-border bg-background">
          <div className="flex shrink-0 items-center justify-between border-b border-border p-4">
            {/* EAI-CUSTOM: gate upload button by kb:upload permission */}
            {can("kb:upload") && (
              <Button
                variant="ghost"
                onClick={() => setShowUpload(true)}
                className="text-foreground hover:text-primary"
              >
                <Plus className="h-4 w-4" />
                添加文件
              </Button>
            )}
            <div className="flex items-center gap-3">
              <div className="relative">
                <Input
                  type="text"
                  placeholder="搜索文件名"
                  value={fileSearch}
                  onChange={(e) => setFileSearch(e.target.value)}
                  className="w-48 pr-8"
                />
                <Search className="absolute top-1/2 right-2.5 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => loadDocs()}
                title="刷新"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon">
                <ArrowRightToLine className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 z-10 bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  <th className="w-10 px-4 py-3 font-medium">
                    <input
                      type="checkbox"
                    />
                  </th>
                  <th className="px-4 py-3 font-medium">文件名</th>
                  <th className="w-28 px-4 py-3 font-medium">上传时间</th>
                  <th className="w-16 px-4 py-3 font-medium">状态</th>
                  <th className="w-20 px-4 py-3 text-right font-medium">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {docsLoading ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-sm text-muted-foreground"
                    >
                      <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                    </td>
                  </tr>
                ) : filteredDocs.length === 0 ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-sm text-muted-foreground"
                    >
                      暂无文件
                    </td>
                  </tr>
                ) : (
                  filteredDocs.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={() => setShowChunksDoc(doc)}
                      className="group cursor-pointer transition-colors hover:bg-muted/50"
                    >
                      <td
                        className="px-4 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          className="w-4 h-4 shrink-0 rounded border-input focus:ring-2 focus:ring-ring/30 focus:ring-offset-0"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-primary text-primary-foreground">
                            <span className="text-[10px] leading-none font-bold">
                              {doc.file_type?.toUpperCase().slice(0, 1) ?? "F"}
                            </span>
                          </div>
                          <div className="min-w-0">
                            <span className="block truncate text-foreground">
                              {doc.name}
                            </span>
                            {doc.file_size > 0 && (
                              <span className="text-[10px] text-muted-foreground">
                                {formatFileSize(doc.file_size)}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {formatDate(doc.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <DocStatusBadge status={doc.status} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          {/* EAI-CUSTOM: gate doc-delete button by kb:delete permission */}
                          {can("kb:delete") && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={(e) => handleDeleteDoc(doc.id, e)}
                              className="text-muted-foreground hover:text-destructive"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex shrink-0 items-center justify-end border-t border-border p-3 text-xs text-muted-foreground">
            共 {docs.length} 个文件
          </div>
        </div>
      </div>

      {/* Right Pane */}
      <div className="flex w-1/2 flex-col overflow-hidden rounded-xl border border-border bg-background">
        <Tabs defaultValue="test" className="flex flex-1 flex-col overflow-hidden">
          <TabsList variant="line" className="shrink-0 justify-start rounded-none border-b border-border px-4">
            <TabsTrigger value="test">检索测试</TabsTrigger>
            <TabsTrigger value="config">检索配置</TabsTrigger>
          </TabsList>
          <TabsContent value="test" className="m-0 flex flex-1 flex-col gap-4 overflow-auto bg-muted/30 p-4">
            <div className="flex flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
              <Textarea
                className="min-h-[120px] w-full resize-none border-0 p-4 text-sm outline-none"
                placeholder="输入查询内容..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey))
                    handleSearch();
                }}
              />
              <div className="flex items-center justify-between border-t border-border bg-muted/50 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
                    格式化
                  </span>
                  <button
                    onClick={() => setIsFormatted(!isFormatted)}
                    className={cn(
                      "relative h-4 w-8 rounded-full transition-colors",
                      isFormatted ? "bg-primary" : "bg-muted-foreground/30",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white transition-transform",
                        isFormatted ? "translate-x-4" : "translate-x-0",
                      )}
                    />
                  </button>
                </div>
                <Button
                  size="icon"
                  onClick={handleSearch}
                  disabled={chatLoading || !query.trim()}
                  className="rounded-full"
                >
                  {chatLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <SearchIcon className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            {chatResult && (
              <div className="space-y-3">
                {chatResult.answer && (
                  <div className="rounded-xl border border-primary/10 bg-primary/5 p-4">
                    <h4 className="mb-2 text-sm font-medium text-foreground">
                      回答
                    </h4>
                    <p className="text-sm whitespace-pre-wrap text-foreground/80">
                      {chatResult.answer}
                    </p>
                  </div>
                )}
                {chatResult.sources && chatResult.sources.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-sm font-medium text-foreground">
                      参考来源
                    </h4>
                    <div className="space-y-2">
                      {chatResult.sources.map((src, idx) => (
                        <div
                          key={idx}
                          onClick={() => setPreviewChunk({ content: src.content ?? "", name: src.document_name })}
                          className="cursor-pointer rounded-lg border border-border bg-background p-3 text-xs transition-colors hover:border-primary/40 hover:bg-muted/40"
                        >
                          <div className="mb-1 font-medium text-foreground/80">
                            {src.document_name ?? `来源 ${idx + 1}`}
                          </div>
                          <p className="line-clamp-3 text-muted-foreground">
                            {src.content}
                          </p>
                          {src.score != null && (
                            <div className="mt-1 text-muted-foreground/70">
                              相似度: {(src.score * 100).toFixed(1)}%
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            {previewChunk && (
              <div
                className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
                onClick={() => setPreviewChunk(null)}
              >
                <div
                  className="max-h-[70vh] w-full max-w-2xl overflow-auto rounded-xl border border-border bg-background p-5"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="mb-2 flex items-center justify-between">
                    <h4 className="text-sm font-medium text-foreground">
                      {previewChunk.name ?? "分块原文"}
                    </h4>
                    <button
                      onClick={() => setPreviewChunk(null)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  <p className="whitespace-pre-wrap text-sm text-foreground/80">
                    {previewChunk.content}
                  </p>
                </div>
              </div>
            )}
          </TabsContent>
          <TabsContent value="config" className="m-0 flex flex-1 flex-col gap-4 overflow-auto bg-muted/30 p-4">
            <div className="space-y-5">
              <div className="space-y-5 rounded-xl border border-border bg-background p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Settings className="h-4 w-4 text-muted-foreground" />
                  检索参数
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    Top K{" "}
                    <span className="font-normal text-muted-foreground">
                      （返回结果数量）
                    </span>
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={1}
                      max={20}
                      value={topK}
                      onChange={(e) => {
                        setTopK(Number(e.target.value));
                        markDirty();
                      }}
                      className="flex-1 accent-primary"
                    />
                    <span className="w-8 text-center text-sm font-medium text-foreground">
                      {topK}
                    </span>
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    相似度阈值{" "}
                    <span className="font-normal text-muted-foreground">
                      （过滤低相关结果）
                    </span>
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={similarityThreshold}
                      onChange={(e) => {
                        setSimilarityThreshold(Number(e.target.value));
                        markDirty();
                      }}
                      className="flex-1 accent-primary"
                    />
                    <span className="w-10 text-center text-sm font-medium text-foreground">
                      {similarityThreshold.toFixed(2)}
                    </span>
                  </div>
                </div>
                {/* 向量权重 */}
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    向量权重{" "}
                    <span className="font-normal text-muted-foreground">
                      （向量/关键词检索权重）
                    </span>
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={vectorWeight}
                      onChange={(e) => {
                        setVectorWeight(Number(e.target.value));
                        markDirty();
                      }}
                      className="flex-1 accent-primary"
                    />
                    <span className="w-10 text-center text-sm font-medium text-foreground">
                      {vectorWeight.toFixed(2)}
                    </span>
                  </div>
                </div>
                {/* 保存 / 重置 */}
                <div className="flex items-center gap-2 pt-2">
                  <button
                    type="button"
                    disabled={configSaving || !configDirty}
                    onClick={handleSaveConfig}
                    className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
                  >
                    {configSaving ? "保存中…" : "保存配置"}
                  </button>
                  <button
                    type="button"
                    disabled={!configDirty}
                    onClick={handleResetConfig}
                    className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground disabled:opacity-50"
                  >
                    重置
                  </button>
                </div>
              </div>

              <div className="space-y-4 rounded-xl border border-border bg-background p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  知识库信息
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    {
                      label: "知识库类型",
                      value: knowledgeBaseTypeLabel(kb.kb_type),
                    },
                    { label: "分块方式", value: kb.chunk_method || "naive" },
                    { label: "访问权限", value: kb.access_type },
                    { label: "嵌入模型", value: kb.embedding_model || "默认" },
                    {
                      label: "分块大小",
                      value: kb.parser_config?.chunk_token_num ? `${kb.parser_config.chunk_token_num} tokens` : "默认",
                    },
                    {
                      label: "PDF 解析",
                      value: kb.parser_config?.layout_recognize || "默认",
                    },
                    {
                      label: "创建时间",
                      value: new Date(kb.created_at).toLocaleDateString(
                        "zh-CN",
                      ),
                    },
                  ].map(({ label, value }) => (
                    <div
                      key={label}
                      className="rounded-lg border border-border bg-muted/50 p-3"
                    >
                      <div className="mb-1 text-xs text-muted-foreground">{label}</div>
                      <div className="text-sm font-medium text-foreground">
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Data access grants (EAI-CUSTOM Task 8) — owner|admin only */}
              {canManageGrants && (
                <div className="space-y-4 rounded-xl border border-border bg-background p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <Settings className="h-4 w-4 text-muted-foreground" />
                      数据访问授权
                    </div>
                    <button
                      type="button"
                      onClick={openAddGrant}
                      className="rounded-lg border border-primary/20 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
                    >
                      + 添加授权
                    </button>
                  </div>
                  {kbGrants.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      暂无显式授权。私有知识库可在此授权特定用户/部门/角色访问。
                    </p>
                  ) : (
                    <div className="space-y-1.5">
                      {kbGrants.map((g) => (
                        <div
                          key={g.id}
                          className="flex items-center justify-between gap-2 text-sm"
                        >
                          <span className="inline-flex min-w-0 items-center gap-1.5">
                            <span
                              className={cn(
                                "shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold",
                                g.grantee_type === "user"
                                  ? "border-sky-500/30 bg-sky-500/10 text-sky-600"
                                  : g.grantee_type === "dept"
                                    ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-600"
                                    : "border-primary/20 bg-primary/10 text-primary",
                              )}
                            >
                              {g.grantee_type === "user"
                                ? "用户"
                                : g.grantee_type === "dept"
                                  ? "部门"
                                  : "角色"}
                            </span>
                            <span className="truncate">{granteeName(g)}</span>
                            <span className="text-xs text-muted-foreground">
                              {g.permission === "write" ? "读写" : "只读"}
                            </span>
                            {g.expires_at && new Date(g.expires_at) < new Date() ? (
                              <span className="text-xs text-muted-foreground/60">
                                (已过期)
                              </span>
                            ) : g.expires_at ? (
                              <span className="text-xs text-muted-foreground">
                                至 {new Date(g.expires_at).toLocaleDateString()}
                              </span>
                            ) : null}
                          </span>
                          <button
                            type="button"
                            onClick={() => removeGrant(g)}
                            className="shrink-0 text-muted-foreground transition-colors hover:text-destructive"
                            aria-label={`移除 ${granteeName(g)} 的授权`}
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Upload Modal */}
      <AnimatePresence>
        {showUpload && (
          <UploadModal
            kbId={kb.id}
            chunkMethod={kb.chunk_method}
            onClose={() => setShowUpload(false)}
            onUploaded={loadDocs}
            toast={toast}
          />
        )}
      </AnimatePresence>

      {/* Chunk Modal */}
      <AnimatePresence>
        {showChunksDoc && (
          <ChunkModal
            kbId={kb.id}
            doc={showChunksDoc}
            onClose={() => setShowChunksDoc(null)}
            toast={toast}
          />
        )}
      </AnimatePresence>

      {/* Edit KB Modal */}
      <AnimatePresence>
        {showEditKb && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setShowEditKb(false)}
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
                  onClick={() => setShowEditKb(false)}
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
                  onClick={() => setShowEditKb(false)}
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

      {/* Add Grant Modal (EAI-CUSTOM Task 8) */}
      <AnimatePresence>
        {showAddGrant && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setShowAddGrant(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-md overflow-hidden rounded-2xl bg-background shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-border px-6 py-4">
                <h3 className="text-lg font-semibold text-foreground">
                  添加数据访问授权
                </h3>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowAddGrant(false)}
                >
                  <X className="h-5 w-5" />
                </Button>
              </div>
              <div className="space-y-5 p-6">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    授权类型
                  </label>
                  <CustomSelect
                    value={grantType}
                    onChange={handleGrantTypeChange}
                    options={[
                      {
                        value: "user",
                        label: "用户",
                        icon: <Search className="h-3.5 w-3.5" />,
                      },
                      {
                        value: "dept",
                        label: "部门",
                        icon: <Database className="h-3.5 w-3.5" />,
                      },
                      {
                        value: "role",
                        label: "角色",
                        icon: <Settings className="h-3.5 w-3.5" />,
                      },
                    ]}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    授权对象 <span className="text-destructive">*</span>
                  </label>
                  <Input
                    type="text"
                    placeholder={
                      grantType === "user"
                        ? "搜索用户..."
                        : grantType === "dept"
                          ? "搜索部门..."
                          : "搜索角色..."
                    }
                    value={grantSearch}
                    onChange={(e) => {
                      setGrantSearch(e.target.value);
                      setGrantTargetId("");
                    }}
                    className="w-full"
                  />
                  <div className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-border bg-background">
                    {grantTargets.length === 0 ? (
                      <p className="px-3 py-2 text-xs text-muted-foreground">
                        未找到匹配项
                      </p>
                    ) : (
                      grantTargets.map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => setGrantTargetId(t.id)}
                          className={cn(
                            "flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors",
                            grantTargetId === t.id
                              ? "bg-primary/10 font-medium text-primary"
                              : "text-foreground hover:bg-muted",
                          )}
                        >
                          <span className="truncate">{t.label}</span>
                          {grantTargetId === t.id && (
                            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" />
                          )}
                        </button>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    权限
                  </label>
                  <CustomSelect
                    value={grantPermission}
                    onChange={(v) => setGrantPermission(v as "read" | "write")}
                    options={[
                      { value: "read", label: "只读" },
                      { value: "write", label: "读写" },
                    ]}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">
                    过期时间{" "}
                    <span className="font-normal text-muted-foreground">
                      （可选）
                    </span>
                  </label>
                  <Input
                    type="date"
                    value={grantExpires}
                    onChange={(e) => setGrantExpires(e.target.value)}
                    className="w-full"
                  />
                </div>
              </div>
              <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
                <Button
                  variant="outline"
                  onClick={() => setShowAddGrant(false)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleAddGrant}
                  disabled={!grantTargetId || grantSaving}
                >
                  {grantSaving && <Loader2 className="h-4 w-4 animate-spin" />}
                  确认添加
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <ToastContainer toasts={toasts} onRemove={remove} />
    </div>
  );
}
