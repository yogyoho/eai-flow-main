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
  Info,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Search as SearchIcon,
  Settings,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
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
import { DeptAccessPicker } from "./DeptAccessPicker";
import { DocStatusBadge } from "./DocStatusBadge";
import {
  isGeoSlicesKnowledgeBase,
  isLawKnowledgeBase,
  isReadOnlyKnowledgeBase,
} from "./isLawKnowledgeBase";
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
  // EAI-CUSTOM: 法规标准系统库不提供直接上传,引导去知识工厂导入
  // (spec docs/superpowers/specs/2026-09-04-law-kb-upload-guidance-design.md)
  const isGeoKb = isGeoSlicesKnowledgeBase(kb.name);
  const isLawKb = isLawKnowledgeBase(kb.name); // 法规专属横幅/引导（geo 走自己的横幅）
  const isSystemKb = isReadOnlyKnowledgeBase(kb.name);
  const [isFormatted, setIsFormatted] = useState(false);
  const [query, setQuery] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatResult, setChatResult] = useState<{
    answer?: string;
    sources?: RAGChatResponse["sources"];
  } | null>(null);
  const [previewChunk, setPreviewChunk] = useState<{
    content: string;
    name?: string;
  } | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [fileSearch, setFileSearch] = useState("");
  const [showUpload, setShowUpload] = useState(false);
  const [showEditKb, setShowEditKb] = useState(false);
  const [showChunksDoc, setShowChunksDoc] = useState<Document | null>(null);
  const [editForm, setEditForm] = useState<UpdateKnowledgeBaseRequest>({
    name: kb.name,
    description: kb.description ?? "",
    access_type: kb.access_type,
    allowed_depts: kb.allowed_depts ?? [],
    kb_type: kb.kb_type ?? "ragflow",
  });
  const [editLoading, setEditLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Data access grants (EAI-CUSTOM Task 8) ──────────────────────────────────
  const canManageGrants = is_admin || kb.owner_id === identity.user_id;
  // EAI-CUSTOM: 访问权限编辑仅限 admin 或 owner;非 owner 编辑他人库时隐藏字段且保存不动访问控制
  const canEditAccess = is_admin || kb.owner_id === identity.user_id;
  const [kbGrants, setKbGrants] = useState<KnowledgeBaseGrant[]>([]);
  const [grantUsers, setGrantUsers] = useState<User[]>([]);
  const [grantDepts, setGrantDepts] = useState<Department[]>([]);
  const [grantRoles, setGrantRoles] = useState<Role[]>([]);
  const [showAddGrant, setShowAddGrant] = useState(false);
  const [grantType, setGrantType] = useState<"user" | "dept" | "role">("user");
  const [grantTargetId, setGrantTargetId] = useState("");
  const [grantSearch, setGrantSearch] = useState("");
  const [grantPermission, setGrantPermission] = useState<"read" | "write">(
    "read",
  );
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
        return u?.full_name ?? u?.username ?? g.grantee_id;
      }
      if (g.grantee_type === "dept") {
        const d = grantDepts.find((x) => x.id === g.grantee_id);
        return d?.name ?? d?.code ?? g.grantee_id;
      }
      const r = grantRoles.find((x) => x.id === g.grantee_id);
      return r?.name ?? r?.code ?? g.grantee_id;
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
        .map((u) => ({ id: u.id, label: u.full_name ?? u.username ?? u.id }));
    }
    if (grantType === "dept") {
      return grantDepts
        .filter(
          (d) =>
            !q ||
            d.name.toLowerCase().includes(q) ||
            (d.code ?? "").toLowerCase().includes(q),
        )
        .map((d) => ({ id: d.id, label: d.name ?? d.code ?? d.id }));
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
    } catch (e) {
      toast((e as { message?: string })?.message ?? "添加授权失败", "error");
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
    } catch (e) {
      toast((e as { message?: string })?.message ?? "移除授权失败", "error");
    }
  };

  useEffect(() => {
    setEditForm({
      name: kb.name,
      description: kb.description ?? "",
      access_type: kb.access_type,
      allowed_depts: kb.allowed_depts ?? [],
      kb_type: kb.kb_type ?? "ragflow",
    });
  }, [
    kb.id,
    kb.name,
    kb.description,
    kb.kb_type,
    kb.access_type,
    kb.allowed_depts,
  ]);

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
    } catch (e) {
      toast((e as { message?: string })?.message ?? "加载文档失败", "error");
      return [];
    } finally {
      setDocsLoading(false);
    }
  }, [kb.id, toast]);

  useEffect(() => {
    void loadDocs();
  }, [loadDocs]);

  // Poll while any doc is in processing state
  useEffect(() => {
    const hasProcessing = docs.some((d) =>
      ["uploading", "processing", "pending"].includes(d.status),
    );
    if (hasProcessing && !pollRef.current) {
      pollRef.current = setInterval(() => {
        void loadDocs();
      }, 3000);
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
    } catch (e) {
      toast((e as { message?: string })?.message ?? "删除失败", "error");
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
      // EAI-CUSTOM: 系统级只读库(法规/地质切片)或非 owner/admin 编辑他人库守恒——
      // 提交体不含 access_type/allowed_depts,只保存名称/描述/kb_type,防串改访问控制
      if (isSystemKb || !canEditAccess) {
        const updated = await kbApi.update(kb.id, {
          name: editForm.name,
          description: editForm.description,
          kb_type: editForm.kb_type,
        });
        onKbUpdated?.(updated);
        toast("知识库信息已更新", "success");
        setShowEditKb(false);
        return;
      }
      // EAI-CUSTOM: dept 提交 allowed_depts;切回私有/公开显式置 [] 清残留
      const isDept = (editForm.access_type ?? "private") === "dept";
      const allowedDepts = isDept
        ? is_admin
          ? (editForm.allowed_depts ?? [])
          : identity.dept_ids
        : [];
      if (isDept && allowedDepts.length === 0) {
        toast(
          is_admin ? "至少选择一个部门" : "你尚未加入任何部门,无法设置部门可见",
          "error",
        );
        setEditLoading(false);
        return;
      }
      const updated = await kbApi.update(kb.id, {
        ...editForm,
        allowed_depts: allowedDepts,
      });
      onKbUpdated?.(updated);
      toast("知识库信息已更新", "success");
      setShowEditKb(false);
    } catch (e) {
      toast((e as { message?: string })?.message ?? "更新失败", "error");
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
        <div className="border-border bg-background shrink-0 rounded-xl border p-6">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="icon" onClick={onBack}>
                <ChevronLeft className="h-5 w-5" />
              </Button>
              <h2 className="text-foreground text-lg font-semibold">
                {kb.name}
              </h2>
              <span className="bg-muted text-muted-foreground rounded px-2 py-1 font-mono text-xs">
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
          <p className="text-muted-foreground text-sm">
            {/* EAI-CUSTOM: truthiness check via .length (not `??`) — description can legitimately be "" (create form defaults to ""), placeholder must still show */}
            {kb.description?.length ? kb.description : "暂无描述"}
          </p>
          {isLawKb && (
            <p className="text-muted-foreground mt-2 flex items-start gap-1.5 text-xs">
              <Info className="text-info mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                本库为法规标准系统知识库,不提供直接上传。法规/标准文件请在
                <Link
                  href="/knowledge-factory?tab=law"
                  className="text-primary hover:underline focus-visible:underline"
                >
                  知识工厂 → 法规标准
                </Link>
                中导入——自动登记元数据(标准号/类型/行业等)并同步到本库。
              </span>
            </p>
          )}
          {isGeoKb && (
            <p className="text-muted-foreground mt-2 flex items-start gap-1.5 text-xs">
              <Info className="text-info mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                本库为地质切片系统知识库（只读）。切片由样例过审后在
                <Link
                  href="/geo-samples"
                  className="text-primary hover:underline focus-visible:underline"
                >
                  地质样例库
                </Link>
                中点击「编译」自动写入并分发
                RAGFlow——如需新增内容，请上传样例并编译。
              </span>
            </p>
          )}
        </div>

        {/* File List Card */}
        <div className="border-border bg-background flex flex-1 flex-col overflow-hidden rounded-xl border">
          <div className="border-border flex shrink-0 items-center justify-between border-b p-4">
            {/* EAI-CUSTOM: gate upload button by kb:upload permission;
                法规标准系统库不提供直接上传(孤儿文档会绕过 Law 元数据层) */}
            {can("kb:upload") && !isSystemKb && (
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
                <Search className="text-muted-foreground absolute top-1/2 right-2.5 h-4 w-4 -translate-y-1/2" />
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
              <thead className="bg-muted/50 text-muted-foreground sticky top-0 z-10 text-xs">
                <tr>
                  <th className="w-10 px-4 py-3 font-medium">
                    <input type="checkbox" />
                  </th>
                  <th className="px-4 py-3 font-medium">文件名</th>
                  <th className="w-28 px-4 py-3 font-medium">上传时间</th>
                  <th className="w-16 px-4 py-3 font-medium">状态</th>
                  <th className="w-20 px-4 py-3 text-right font-medium">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {docsLoading ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="text-muted-foreground px-4 py-8 text-center text-sm"
                    >
                      <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                    </td>
                  </tr>
                ) : filteredDocs.length === 0 ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="text-muted-foreground px-4 py-8 text-center text-sm"
                    >
                      暂无文件
                    </td>
                  </tr>
                ) : (
                  filteredDocs.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={() => setShowChunksDoc(doc)}
                      className="group hover:bg-muted/50 cursor-pointer transition-colors"
                    >
                      <td
                        className="px-4 py-3"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          className="border-input focus:ring-ring/30 h-4 w-4 shrink-0 rounded focus:ring-2 focus:ring-offset-0"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="bg-primary text-primary-foreground flex h-6 w-6 shrink-0 items-center justify-center rounded">
                            <span className="text-[10px] leading-none font-bold">
                              {doc.file_type?.toUpperCase().slice(0, 1) ?? "F"}
                            </span>
                          </div>
                          <div className="min-w-0">
                            <span className="text-foreground block truncate">
                              {doc.name}
                            </span>
                            {doc.file_size > 0 && (
                              <span className="text-muted-foreground text-[10px]">
                                {formatFileSize(doc.file_size)}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="text-muted-foreground px-4 py-3 text-xs">
                        {formatDate(doc.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <DocStatusBadge status={doc.status} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          {/* EAI-CUSTOM: gate doc-delete button by kb:delete permission;
                              法规标准系统库文档为 laws 投影,删除会造成 laws.ragflow_document_id 悬空
                              (后端删除接口对 laws 投影文档本就 404,此处为 UX 层引导) */}
                          {can("kb:delete") && !isSystemKb && (
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

          <div className="border-border text-muted-foreground flex shrink-0 items-center justify-end border-t p-3 text-xs">
            共 {docs.length} 个文件
          </div>
        </div>
      </div>

      {/* Right Pane */}
      <div className="border-border bg-background flex w-1/2 flex-col overflow-hidden rounded-xl border">
        <Tabs
          defaultValue="test"
          className="flex flex-1 flex-col overflow-hidden"
        >
          <TabsList
            variant="line"
            className="border-border shrink-0 justify-start rounded-none border-b px-4"
          >
            <TabsTrigger value="test">检索测试</TabsTrigger>
            <TabsTrigger value="config">检索配置</TabsTrigger>
          </TabsList>
          <TabsContent
            value="test"
            className="bg-muted/30 m-0 flex flex-1 flex-col gap-4 overflow-auto p-4"
          >
            <div className="border-border bg-background focus-within:border-primary focus-within:ring-primary flex flex-col overflow-hidden rounded-xl border shadow-sm transition-all focus-within:ring-1">
              <Textarea
                className="min-h-[120px] w-full resize-none border-0 p-4 text-sm outline-none"
                placeholder="输入查询内容..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey))
                    void handleSearch();
                }}
              />
              <div className="border-border bg-muted/50 flex items-center justify-between border-t px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="bg-primary text-primary-foreground rounded-full px-2 py-0.5 text-xs font-medium">
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
                  <div className="border-primary/10 bg-primary/5 rounded-xl border p-4">
                    <h4 className="text-foreground mb-2 text-sm font-medium">
                      回答
                    </h4>
                    <p className="text-foreground/80 text-sm whitespace-pre-wrap">
                      {chatResult.answer}
                    </p>
                  </div>
                )}
                {chatResult.sources && chatResult.sources.length > 0 && (
                  <div>
                    <h4 className="text-foreground mb-2 text-sm font-medium">
                      参考来源
                    </h4>
                    <div className="space-y-2">
                      {chatResult.sources.map((src, idx) => (
                        <div
                          key={idx}
                          onClick={() =>
                            setPreviewChunk({
                              content: src.content ?? "",
                              name: src.document_name,
                            })
                          }
                          className="border-border bg-background hover:border-primary/40 hover:bg-muted/40 cursor-pointer rounded-lg border p-3 text-xs transition-colors"
                        >
                          <div className="text-foreground/80 mb-1 font-medium">
                            {src.document_name ?? `来源 ${idx + 1}`}
                          </div>
                          <p className="text-muted-foreground line-clamp-3">
                            {src.content}
                          </p>
                          {src.score != null && (
                            <div className="text-muted-foreground/70 mt-1">
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
                  className="border-border bg-background max-h-[70vh] w-full max-w-2xl overflow-auto rounded-xl border p-5"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="mb-2 flex items-center justify-between">
                    <h4 className="text-foreground text-sm font-medium">
                      {previewChunk.name ?? "分块原文"}
                    </h4>
                    <button
                      onClick={() => setPreviewChunk(null)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  <p className="text-foreground/80 text-sm whitespace-pre-wrap">
                    {previewChunk.content}
                  </p>
                </div>
              </div>
            )}
          </TabsContent>
          <TabsContent
            value="config"
            className="bg-muted/30 m-0 flex flex-1 flex-col gap-4 overflow-auto p-4"
          >
            <div className="space-y-5">
              <div className="border-border bg-background space-y-5 rounded-xl border p-5">
                <div className="text-foreground flex items-center gap-2 text-sm font-semibold">
                  <Settings className="text-muted-foreground h-4 w-4" />
                  检索参数
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    Top K{" "}
                    <span className="text-muted-foreground font-normal">
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
                      className="accent-primary flex-1"
                    />
                    <span className="text-foreground w-8 text-center text-sm font-medium">
                      {topK}
                    </span>
                  </div>
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    相似度阈值{" "}
                    <span className="text-muted-foreground font-normal">
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
                      className="accent-primary flex-1"
                    />
                    <span className="text-foreground w-10 text-center text-sm font-medium">
                      {similarityThreshold.toFixed(2)}
                    </span>
                  </div>
                </div>
                {/* 向量权重 */}
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    向量权重{" "}
                    <span className="text-muted-foreground font-normal">
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
                      className="accent-primary flex-1"
                    />
                    <span className="text-foreground w-10 text-center text-sm font-medium">
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
                    className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                  >
                    {configSaving ? "保存中…" : "保存配置"}
                  </button>
                  <button
                    type="button"
                    disabled={!configDirty}
                    onClick={handleResetConfig}
                    className="border-border text-foreground rounded-md border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                  >
                    重置
                  </button>
                </div>
              </div>

              <div className="border-border bg-background space-y-4 rounded-xl border p-5">
                <div className="text-foreground flex items-center gap-2 text-sm font-semibold">
                  <Database className="text-muted-foreground h-4 w-4" />
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
                    { label: "嵌入模型", value: kb.embedding_model ?? "默认" },
                    {
                      label: "分块大小",
                      value: kb.parser_config?.chunk_token_num
                        ? `${kb.parser_config.chunk_token_num} tokens`
                        : "默认",
                    },
                    {
                      label: "PDF 解析",
                      value: kb.parser_config?.layout_recognize ?? "默认",
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
                      className="border-border bg-muted/50 rounded-lg border p-3"
                    >
                      <div className="text-muted-foreground mb-1 text-xs">
                        {label}
                      </div>
                      <div className="text-foreground text-sm font-medium">
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Data access grants (EAI-CUSTOM Task 8) — owner|admin only */}
              {canManageGrants && (
                <div className="border-border bg-background space-y-4 rounded-xl border p-5">
                  <div className="flex items-center justify-between">
                    <div className="text-foreground flex items-center gap-2 text-sm font-semibold">
                      <Settings className="text-muted-foreground h-4 w-4" />
                      数据访问授权
                    </div>
                    <button
                      type="button"
                      onClick={openAddGrant}
                      className="border-primary/20 bg-primary/10 text-primary hover:bg-primary/20 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors"
                    >
                      + 添加授权
                    </button>
                  </div>
                  {kbGrants.length === 0 ? (
                    <p className="text-muted-foreground text-xs">
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
                            <span className="text-muted-foreground text-xs">
                              {g.permission === "write" ? "读写" : "只读"}
                            </span>
                            {g.expires_at &&
                            new Date(g.expires_at) < new Date() ? (
                              <span className="text-muted-foreground/60 text-xs">
                                (已过期)
                              </span>
                            ) : g.expires_at ? (
                              <span className="text-muted-foreground text-xs">
                                至 {new Date(g.expires_at).toLocaleDateString()}
                              </span>
                            ) : null}
                          </span>
                          <button
                            type="button"
                            onClick={() => removeGrant(g)}
                            className="text-muted-foreground hover:text-destructive shrink-0 transition-colors"
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
              className="bg-background relative w-full max-w-lg overflow-hidden rounded-2xl shadow-xl"
            >
              <div className="border-border flex items-center justify-between border-b px-6 py-4">
                <h3 className="text-foreground text-lg font-semibold">
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
                  <label className="text-foreground mb-1 block text-sm font-medium">
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
                  <label className="text-foreground mb-1 block text-sm font-medium">
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
                {/* EAI-CUSTOM: 系统级只读库(法规/地质切片)不提供访问权限编辑,防串改访问控制;
                    非 owner/admin 编辑他人库同样隐藏 */}
                {!isSystemKb && canEditAccess && (
                  <>
                    <div>
                      <label className="text-foreground mb-1 block text-sm font-medium">
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
                    {(editForm.access_type ?? "private") === "dept" && (
                      <div className="mt-2">
                        <DeptAccessPicker
                          selectedIds={
                            is_admin
                              ? (editForm.allowed_depts ?? [])
                              : identity.dept_ids
                          }
                          onChange={(ids) =>
                            setEditForm({ ...editForm, allowed_depts: ids })
                          }
                          readOnly={!is_admin}
                        />
                      </div>
                    )}
                  </>
                )}
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
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
              <div className="border-border bg-muted/50 flex items-center justify-end gap-3 border-t px-6 py-4">
                <Button variant="outline" onClick={() => setShowEditKb(false)}>
                  取消
                </Button>
                <Button
                  onClick={handleEditSave}
                  disabled={
                    !editForm.name?.trim() ||
                    editLoading ||
                    (!isSystemKb &&
                      canEditAccess &&
                      (editForm.access_type ?? "private") === "dept" &&
                      (is_admin
                        ? (editForm.allowed_depts ?? [])
                        : identity.dept_ids
                      ).length === 0)
                  }
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
              className="bg-background relative w-full max-w-md overflow-hidden rounded-2xl shadow-xl"
            >
              <div className="border-border flex items-center justify-between border-b px-6 py-4">
                <h3 className="text-foreground text-lg font-semibold">
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
                  <label className="text-foreground mb-1 block text-sm font-medium">
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
                  <label className="text-foreground mb-1 block text-sm font-medium">
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
                  <div className="border-border bg-background mt-2 max-h-48 overflow-y-auto rounded-lg border">
                    {grantTargets.length === 0 ? (
                      <p className="text-muted-foreground px-3 py-2 text-xs">
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
                              ? "bg-primary/10 text-primary font-medium"
                              : "text-foreground hover:bg-muted",
                          )}
                        >
                          <span className="truncate">{t.label}</span>
                          {grantTargetId === t.id && (
                            <CheckCircle2 className="text-primary h-3.5 w-3.5 shrink-0" />
                          )}
                        </button>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <label className="text-foreground mb-1 block text-sm font-medium">
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
                  <label className="text-foreground mb-1 block text-sm font-medium">
                    过期时间{" "}
                    <span className="text-muted-foreground font-normal">
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
              <div className="border-border bg-muted/50 flex items-center justify-end gap-3 border-t px-6 py-4">
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
