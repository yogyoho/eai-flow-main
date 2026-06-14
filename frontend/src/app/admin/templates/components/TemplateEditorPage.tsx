"use client";

import { ArrowLeft, ChevronDown, ChevronUp, Loader2, CheckCircle2, Send, Save, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AdminSelect } from "@/components/ui/admin-select";
import { PageLoadingOverlay } from "@/components/ui/page-loading-overlay";
import { deptApi } from "@/extensions/api/index";
import { workflowApi } from "@/extensions/workflow/api";
import { WorkflowEditor, type WorkflowEditorHandle } from "@/extensions/workflow/WorkflowEditor";
import type { WorkflowGraph } from "@/extensions/workflow/types";
import { isLegacyGraph, migrateLegacyToUnified } from "@/extensions/workflow/templates/migration";
import { useReportTypes } from "@/extensions/project/hooks/useReportTypes";
import { useAuth } from "@/extensions/hooks/useAuth";

interface DeptItem {
  id: string;
  name: string;
  code: string | null;
}

interface TemplateEditorPageProps {
  templateId?: string;
}

export function TemplateEditorPage({ templateId }: TemplateEditorPageProps) {
  const router = useRouter();
  const { user } = useAuth();
  const isSuperAdmin = user?.role_name === "Super Admin";

  const { options: reportTypeOptions } = useReportTypes();

  const editorRef = useRef<WorkflowEditorHandle>(null);

  const [name, setName] = useState("");
  const [reportType, setReportType] = useState<string>("");
  const [description, setDescription] = useState("");
  const [visibleDeptIds, setVisibleDeptIds] = useState<string[]>([]);
  const [templateStatus, setTemplateStatus] = useState<string>("draft");
  const [orgBindings, setOrgBindings] = useState<Record<string, { deptCode?: string }>>({});

  const [initialGraphJson, setInitialGraphJson] = useState<WorkflowGraph | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(!!templateId);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [bottomOpen, setBottomOpen] = useState(true);

  const [departments, setDepartments] = useState<DeptItem[]>([]);
  useEffect(() => {
    deptApi.list({ limit: 100 }).then((res) => {
      // The API returns a tree (parent nodes with children). Flatten it.
      const tree = (res.departments || []) as Array<DeptItem & { children?: DeptItem[] }>;
      const flat: DeptItem[] = [];
      for (const node of tree) {
        flat.push({ id: node.id, name: node.name, code: node.code });
        if (node.children) {
          for (const child of node.children) {
            flat.push({ id: child.id, name: `　${child.name}`, code: child.code });
          }
        }
      }
      setDepartments(flat);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!templateId) return;
    setIsLoading(true);
    workflowApi
      .get(templateId)
      .then((def) => {
        setName(def.name);
        setReportType(def.reportType || "");
        setDescription(def.description || "");
        setVisibleDeptIds(def.visibleDeptIds || []);
        setTemplateStatus(def.templateStatus || "draft");
        setOrgBindings(def.orgBindings || {});
        if (def.graphJson) {
          // Auto-migrate legacy v1 flat graphs to v2
          const raw = def.graphJson as Record<string, unknown>;
          let graph: WorkflowGraph;
          if (isLegacyGraph(raw)) {
            graph = migrateLegacyToUnified(raw as Parameters<typeof migrateLegacyToUnified>[0]);
          } else {
            graph = def.graphJson;
          }
          setInitialGraphJson(graph);
        }
      })
      .catch((err) => {
        console.error(err);
        toast.error("加载模板失败");
      })
      .finally(() => setIsLoading(false));
  }, [templateId]);

  const handleOrgBindingChange = useCallback((nodeId: string, deptCode: string | null) => {
    setOrgBindings((prev) => {
      const next = { ...prev };
      if (deptCode) {
        next[nodeId] = { deptCode };
      } else {
        delete next[nodeId];
      }
      return next;
    });
  }, []);

  const handleSave = useCallback(
    async (_name: string, graphJson: WorkflowGraph) => {
      setSaving(true);
      try {
        if (templateId) {
          await workflowApi.update(templateId, {
            name: _name || name,
            graphJson,
            orgBindings,
            description,
            visibleDeptIds: visibleDeptIds.length > 0 ? visibleDeptIds : null,
          });
          toast.success("模板已保存");
        } else {
          const created = await workflowApi.create({
            name: _name || name || "新工作流模板",
            graphJson,
            isTemplate: true,
            orgBindings,
            description,
            visibleDeptIds: visibleDeptIds.length > 0 ? visibleDeptIds : null,
            reportType: reportType || null,
          });
          toast.success("模板已创建");
          router.replace(`/admin/templates/${created.id}`);
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "保存失败");
      } finally {
        setSaving(false);
      }
    },
    [templateId, name, orgBindings, description, visibleDeptIds, reportType, router],
  );

  const handlePublish = useCallback(async () => {
    if (!templateId) return;
    setSaving(true);
    try {
      if (isSuperAdmin) {
        await workflowApi.publishTemplate(templateId);
        toast.success("模板已发布");
        setTemplateStatus("published");
      } else {
        await workflowApi.submitApproval(templateId);
        toast.success("已提交审批");
        setTemplateStatus("pending_approval");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败");
    } finally {
      setSaving(false);
    }
  }, [templateId, isSuperAdmin]);

  const handleToolbarValidate = useCallback(async () => {
    if (!editorRef.current) return;
    setValidating(true);
    try {
      await editorRef.current.validate();
    } finally {
      setValidating(false);
    }
  }, []);

  const handleToolbarSave = useCallback(async () => {
    if (!editorRef.current) return;
    try {
      await editorRef.current.save();
    } catch {
      // error handled inside WorkflowEditor
    }
  }, []);

  if (isLoading) {
    return <PageLoadingOverlay text="加载模板" />;
  }

  const statusLabel: Record<string, { text: string; color: string }> = {
    draft: { text: "草稿", color: "bg-gray-100 text-gray-600 border-gray-200" },
    pending_approval: { text: "待审批", color: "bg-amber-50 text-amber-600 border-amber-200" },
    published: { text: "已发布", color: "bg-green-50 text-green-600 border-green-200" },
    rejected: { text: "已拒绝", color: "bg-red-50 text-red-600 border-red-200" },
  };
  const st = statusLabel[templateStatus] ?? statusLabel.draft!;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Top toolbar — replaces the hidden DAG internal toolbar */}
      <div className="shrink-0 border-b border-border bg-card px-4 py-2.5 flex items-center gap-3">
        <Link
          href="/admin/templates"
          className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>

        <div className="w-px h-5 bg-border" />

        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="模板名称"
          className="px-3 py-1.5 text-sm font-medium border border-border rounded-lg bg-background w-60 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-colors"
        />

        <AdminSelect
          value={reportType}
          onChange={(v) => setReportType(v)}
          options={reportTypeOptions}
          placeholder="选择报告类型"
          className="w-auto min-w-[6rem]"
        />

        <span className={`text-[10px] font-medium px-2.5 py-1 rounded-full border ${st.color}`}>
          {st.text}
        </span>

        <div className="flex-1" />

        <button
          onClick={handleToolbarValidate}
          disabled={validating}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg hover:bg-amber-100 transition-colors disabled:opacity-50"
        >
          {validating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
          校验
        </button>

        <button
          onClick={handleToolbarSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          保存
        </button>

        <button
          onClick={handlePublish}
          disabled={saving || templateStatus === "published" || templateStatus === "pending_approval"}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary-foreground bg-primary rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isSuperAdmin ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Send className="w-3.5 h-3.5" />}
          {templateStatus === "published" ? "已发布" : isSuperAdmin ? "发布" : "提交审批"}
        </button>
      </div>

      {/* DAG editor — built-in toolbar hidden, controlled via ref */}
      <div className="flex-1 min-h-0">
        <WorkflowEditor
          ref={editorRef}
          initialGraphJson={initialGraphJson}
          initialName={name}
          onSave={handleSave}
          onOrgBindingChange={handleOrgBindingChange}
          orgBindings={orgBindings}
          hideToolbar
        />
      </div>

      {/* Bottom settings panel */}
      <div className="shrink-0 border-t border-border bg-card">
        <button
          onClick={() => setBottomOpen(!bottomOpen)}
          className="w-full flex items-center justify-between px-5 py-2 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
        >
          <span className="uppercase tracking-wider">模板设置</span>
          {bottomOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
        </button>
        {bottomOpen && (
          <div className="px-5 pb-4 pt-1 flex items-start gap-5">
            <div className="flex-1">
              <label className="text-[11px] font-medium text-muted-foreground block mb-1.5">模板描述</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="描述此模板的用途和适用场景..."
                rows={2}
                className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-background resize-none focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-colors"
              />
            </div>
            <div className="w-60">
              <label className="text-[11px] font-medium text-muted-foreground block mb-1.5">可见部门（留空 = 全部可见）</label>
              <div className="max-h-24 overflow-y-auto border border-border rounded-lg bg-background p-2 space-y-0.5">
                {departments.map((dept) => (
                  <label key={dept.id} className="flex items-center gap-2 text-xs cursor-pointer py-0.5 px-1 rounded hover:bg-muted/50 transition-colors">
                    <input
                      type="checkbox"
                      checked={visibleDeptIds.includes(dept.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setVisibleDeptIds((prev) => [...prev, dept.id]);
                        } else {
                          setVisibleDeptIds((prev) => prev.filter((id) => id !== dept.id));
                        }
                      }}
                      className="rounded accent-primary"
                    />
                    {dept.name}
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
