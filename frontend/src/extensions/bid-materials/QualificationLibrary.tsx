"use client";

// EAI-CUSTOM (Plan 4, spec §2.2/2.3): 资质版本库 tab——MinIO 代理上传/版本不可变只追加/回滚=改指针/软删。
// 具名导出 QualificationLibrary——BidMaterials.tsx(tab 壳)以 { QualificationLibrary } 具名导入。契约事实(Plan 4 Task 1 实读):
// qualifications.list 仅 qual_type/include_disabled/limit/offset——无 search 入参, 不渲染搜索框;
// 到期过滤走 expiring(90)(端点仅 days 入参, 类型过滤在其结果上前端补做); 已停用行经 include_disabled 保显(muted+badge);
// rollback 请求体键 to_version; 上传 multipart note ≤200, created=false=sha256 去重命中(幂等返回既有版);
// fileUrl 仅服当前版(后端无 ?version= 参数)——「预览/下载」只挂当前版行; PATCH 不得携带 disabled(400), 软删走 DELETE。

import {
  Ban,
  Clock,
  History,
  Loader2,
  Pencil,
  PlusCircle,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import {
  bidMaterialsApi,
  QUAL_TYPE_PRESETS,
  type QualificationRecord,
  type QualificationUpsertInput,
  type QualificationVersionRecord,
} from "./bid-materials-api";

const PAGE_SIZE = 20;

const EXPIRING_DAYS = 90;

const QUAL_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  QUAL_TYPE_PRESETS.map((t) => [t.value, t.label]),
);

const QUAL_TYPE_FILTER_OPTIONS = [
  { value: "", label: "全部类型" },
  ...QUAL_TYPE_PRESETS,
];

const DAY_MS = 24 * 60 * 60 * 1000;

// 表单态统一为 string（空串→提交时归一为 null），避免受控输入在 null/"" 间抖动
interface QualificationFormState {
  qual_type: string;
  cert_no: string;
  issuer: string;
  valid_until: string;
  scope: string;
  org_scope: string;
  notes: string;
}

function localDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// 有效期配色（ISO YYYY-MM-DD 字符串可直接比较）：过期=红，90 天内=琥珀，其余正常
function validityClass(validUntil: string | null): string {
  if (!validUntil) return "";
  const today = localDateStr(new Date());
  const in90 = localDateStr(new Date(Date.now() + EXPIRING_DAYS * DAY_MS));
  if (validUntil < today) return "text-red-600";
  if (validUntil <= in90) return "text-amber-600";
  return "text-foreground";
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("zh-CN", { hour12: false });
}

export function QualificationLibrary() {
  const [quals, setQuals] = useState<QualificationRecord[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);
  const [qualTypeFilter, setQualTypeFilter] = useState("");
  const [expiringOnly, setExpiringOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editing, setEditing] = useState<QualificationRecord | null>(null);
  const [versionsTarget, setVersionsTarget] =
    useState<QualificationRecord | null>(null);

  const fetchQuals = useCallback(
    async (targetPage = page) => {
      setLoading(true);
      try {
        if (expiringOnly) {
          // expiring 端点仅 days 入参——类型过滤在其结果上前端补做（后端无 qual_type 参数）
          const result =
            await bidMaterialsApi.qualifications.expiring(EXPIRING_DAYS);
          setHasMore(false);
          setQuals(
            qualTypeFilter
              ? result.filter((r) => r.qual_type === qualTypeFilter)
              : result,
          );
        } else {
          // 裸数组响应无 total：limit 多取 1 条探测 hasMore，展示时截断回 PAGE_SIZE
          const result = await bidMaterialsApi.qualifications.list({
            qual_type: qualTypeFilter || undefined,
            include_disabled: true, // 已停用行保显（muted+badge），可追溯
            limit: PAGE_SIZE + 1,
            offset: (targetPage - 1) * PAGE_SIZE,
          });
          setHasMore(result.length > PAGE_SIZE);
          setQuals(result.slice(0, PAGE_SIZE));
        }
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "加载资质列表失败");
      } finally {
        setLoading(false);
      }
    },
    [page, qualTypeFilter, expiringOnly],
  );

  useEffect(() => {
    void fetchQuals();
    // 筛选/页码变化经 fetchQuals 的 useCallback 依赖即拉取
  }, [fetchQuals]);

  const handleDisable = useCallback(
    async (qual: QualificationRecord) => {
      if (
        !window.confirm(
          `确认停用资质「${qual.cert_no}」？停用为软删（仅打 disabled 标记），记录与版本历史保留。`,
        )
      )
        return;
      try {
        await bidMaterialsApi.qualifications.disable(qual.id);
        toast.success("资质已停用");
        void fetchQuals();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "停用失败");
      }
    },
    [fetchQuals],
  );

  // 稳定引用传给 VersionsDialog（其内部 mount-effect 依赖该回调拉取——
  // 若内联箭头每次渲染换身份会触发 refetch 循环）
  const refreshFromDialog = useCallback(() => {
    void fetchQuals();
  }, [fetchQuals]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-foreground text-base font-semibold">
            投标资质库
          </h2>
          <p className="text-muted-foreground mt-1 text-sm">
            MinIO 版本库：版本不可变只追加，回滚=改指针；90 天内到期高亮预警。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void fetchQuals()}
            disabled={loading}
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            刷新
          </Button>
          <Button size="sm" onClick={() => setShowCreateDialog(true)}>
            <PlusCircle className="h-4 w-4" />
            登记资质
          </Button>
        </div>
      </div>

      {/* Filters: 类型下拉（后端透传 qual_type）+ 90 天内到期 toggle（替代 list 走 expiring）——
          list 无 search 入参，不渲染搜索框 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-44">
          <AdminSelect
            value={qualTypeFilter}
            onValueChange={(v) => {
              setQualTypeFilter(v);
              setPage(1);
            }}
            options={QUAL_TYPE_FILTER_OPTIONS}
          />
        </div>
        <Button
          variant={expiringOnly ? "default" : "outline"}
          size="sm"
          onClick={() => {
            setExpiringOnly((v) => !v);
            setPage(1);
          }}
        >
          <Clock className="h-4 w-4" />
          90 天内到期
        </Button>
      </div>

      {/* Table */}
      {loading && quals.length === 0 ? (
        <div className="text-muted-foreground flex items-center justify-center gap-2 py-20 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
        </div>
      ) : quals.length === 0 &&
        page === 1 &&
        !qualTypeFilter &&
        !expiringOnly ? (
        <Empty className="border-border rounded-xl border border-dashed py-16">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ShieldCheck className="h-6 w-6" />
            </EmptyMedia>
            <EmptyTitle>资质库还是空的</EmptyTitle>
            <EmptyDescription>
              登记营业执照、体系认证、业绩证明等资质文件，按版本管理（MinIO
              版本库只追加，支持回滚），90 天内到期自动高亮预警。
            </EmptyDescription>
          </EmptyHeader>
          <div className="flex items-center justify-center gap-2">
            <Button size="sm" onClick={() => setShowCreateDialog(true)}>
              <PlusCircle className="h-4 w-4" />
              登记第一条资质
            </Button>
          </div>
        </Empty>
      ) : (
        <div className="border-border overflow-hidden rounded-xl border">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="bg-muted/50 text-muted-foreground border-border border-b text-left">
                  <th className="px-4 py-3 font-medium">类型</th>
                  <th className="px-4 py-3 font-medium">证号</th>
                  <th className="px-4 py-3 font-medium">发证机构</th>
                  <th className="px-4 py-3 font-medium">有效期至</th>
                  <th className="px-4 py-3 font-medium">当前版</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {quals.map((q) => (
                  <QualificationRow
                    key={q.id}
                    qual={q}
                    onVersions={() => setVersionsTarget(q)}
                    onEdit={() => setEditing(q)}
                    onDisable={() => void handleDisable(q)}
                  />
                ))}
                {quals.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="text-muted-foreground px-4 py-12 text-center"
                    >
                      当前筛选条件下没有资质。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pagination（offset 制——裸数组无 total，只做上一页/下一页；expiring 无分页入参，整表展示） */}
      {!expiringOnly && (quals.length > 0 || page > 1) && (
        <div className="text-muted-foreground flex items-center justify-between text-sm">
          <span>每页 {PAGE_SIZE} 条</span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </Button>
            <span className="tabular-nums">第 {page} 页</span>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasMore || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </Button>
          </div>
        </div>
      )}

      <CreateEditDialog
        open={showCreateDialog || editing !== null}
        editing={editing}
        onClose={() => {
          setShowCreateDialog(false);
          setEditing(null);
        }}
        onSaved={() => {
          setShowCreateDialog(false);
          setEditing(null);
          void fetchQuals();
        }}
      />
      {versionsTarget && (
        <VersionsDialog
          target={versionsTarget}
          onClose={() => setVersionsTarget(null)}
          onChanged={refreshFromDialog}
        />
      )}
    </div>
  );
}

// 单行——已停用行整行 muted+「已停用」badge；操作入口整体隐藏（后端 service._get() 对停用记录一律
// 404，版本历史/编辑/停用点击必败；仅保留行展示供追溯；无恢复端点，误停需另走数据修复）
function QualificationRow({
  qual,
  onVersions,
  onEdit,
  onDisable,
}: {
  qual: QualificationRecord;
  onVersions: () => void;
  onEdit: () => void;
  onDisable: () => void;
}) {
  const disabled = qual.disabled;
  return (
    <tr
      className={cn(
        "border-border hover:bg-muted/30 border-b transition-colors last:border-b-0",
        disabled && "opacity-60",
      )}
    >
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="flex items-center gap-2">
          <span className="text-foreground font-medium">
            {QUAL_TYPE_LABELS[qual.qual_type] ?? qual.qual_type}
          </span>
          {disabled && (
            <Badge
              variant="outline"
              className="border-red-200 bg-red-50 text-red-700"
            >
              已停用
            </Badge>
          )}
        </div>
      </td>
      <td className="max-w-[200px] px-4 py-3">
        <span
          className="text-foreground block truncate font-mono text-xs"
          title={qual.cert_no}
        >
          {qual.cert_no}
        </span>
      </td>
      <td
        className="text-muted-foreground max-w-[180px] truncate px-4 py-3"
        title={qual.issuer ?? undefined}
      >
        {qual.issuer ?? "—"}
      </td>
      <td
        className={cn(
          "px-4 py-3 font-medium whitespace-nowrap tabular-nums",
          validityClass(qual.valid_until),
        )}
      >
        {qual.valid_until ?? "—"}
      </td>
      <td className="text-muted-foreground px-4 py-3 tabular-nums">
        v{qual.current_version}
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-1">
          {/* 已停用行整体隐藏操作入口——后端对停用记录一律 404，版本历史/编辑/停用点击必败 */}
          {!disabled && (
            <>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-primary"
                title="版本历史（上传新版本/回滚/预览下载）"
                onClick={onVersions}
              >
                <History className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-primary"
                title="编辑元数据（类型/证号/机构/有效期等）"
                onClick={onEdit}
              >
                <Pencil className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-red-600"
                title="停用资质（软删）"
                onClick={onDisable}
              >
                <Ban className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

// ============== 登记/编辑资质对话框（创建 create 与编辑 update(PATCH) 复用） ==============

function CreateEditDialog({
  open,
  editing,
  onClose,
  onSaved,
}: {
  open: boolean;
  editing: QualificationRecord | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const emptyForm = useMemo<QualificationFormState>(
    () => ({
      qual_type: "",
      cert_no: "",
      issuer: "",
      valid_until: "",
      scope: "",
      org_scope: "",
      notes: "",
    }),
    [],
  );
  const [form, setForm] = useState<QualificationFormState>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  // 打开时按编辑目标回填（创建则清空）——关闭态不重置，避免关闭动画中表单闪空
  useEffect(() => {
    if (!open) return;
    setForm(
      editing
        ? {
            qual_type: editing.qual_type,
            cert_no: editing.cert_no,
            issuer: editing.issuer ?? "",
            valid_until: editing.valid_until ?? "",
            scope: editing.scope ?? "",
            org_scope: editing.org_scope ?? "",
            notes: editing.notes ?? "",
          }
        : emptyForm,
    );
  }, [open, editing, emptyForm]);

  const setField = (patch: Partial<QualificationFormState>) =>
    setForm((f) => ({ ...f, ...patch }));

  const submit = async () => {
    const certNo = form.cert_no.trim();
    if (!form.qual_type || !certNo) {
      toast.error("请填写资质类型与证号");
      return;
    }
    // 空串归一为 null；PATCH 契约不得携带 disabled(400)——负载只含可编辑元数据字段
    const payload: QualificationUpsertInput = {
      qual_type: form.qual_type,
      cert_no: certNo,
      issuer: form.issuer.trim() || null,
      valid_until: form.valid_until || null,
      scope: form.scope.trim() || null,
      org_scope: form.org_scope.trim() || null,
      notes: form.notes.trim() || null,
    };
    setSubmitting(true);
    try {
      if (editing) {
        await bidMaterialsApi.qualifications.update(editing.id, payload);
        toast.success("资质已更新");
      } else {
        await bidMaterialsApi.qualifications.create(payload);
        toast.success("资质已登记");
      }
      onSaved();
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : editing ? "更新失败" : "登记失败",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? undefined : onClose())}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{editing ? "编辑资质" : "登记资质"}</DialogTitle>
          <DialogDescription>
            {editing
              ? "修改元数据（类型/证号/机构/有效期等）；证照图片经「版本历史」上传新版本管理。"
              : "先登记资质元数据；证照图片在「版本历史」中上传 v1（PNG/JPG）。资质类型为后端闭集，自由文本会被 422。"}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>资质类型 *</Label>
              <AdminSelect
                value={form.qual_type}
                onValueChange={(v) => setField({ qual_type: v })}
                options={QUAL_TYPE_PRESETS}
                placeholder="选择类型"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="qual-cert-no">证号 *</Label>
              <Input
                id="qual-cert-no"
                value={form.cert_no}
                placeholder="如 91110000XXXXXXXXXX"
                onChange={(e) => setField({ cert_no: e.target.value })}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="qual-issuer">发证机构</Label>
              <Input
                id="qual-issuer"
                value={form.issuer}
                placeholder="如 中国新时代认证中心"
                onChange={(e) => setField({ issuer: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="qual-valid-until">有效期至</Label>
              <Input
                id="qual-valid-until"
                type="date"
                value={form.valid_until}
                onChange={(e) => setField({ valid_until: e.target.value })}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="qual-scope">适用范围</Label>
              <Input
                id="qual-scope"
                value={form.scope}
                placeholder="如 软件开发/信息系统集成"
                onChange={(e) => setField({ scope: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="qual-org-scope">组织范围</Label>
              <Input
                id="qual-org-scope"
                value={form.org_scope}
                placeholder="如 公司本部及分支机构"
                onChange={(e) => setField({ org_scope: e.target.value })}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="qual-notes">备注</Label>
            <Textarea
              id="qual-notes"
              rows={2}
              value={form.notes}
              placeholder="证书说明 / 复审安排 / 投标适用性备注"
              onChange={(e) => setField({ notes: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void submit()} disabled={submitting}>
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {editing ? "保存" : "登记"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============== 版本历史对话框（版本列表/当前版预览下载/回滚/上传新版本） ==============

function VersionsDialog({
  target,
  onClose,
  onChanged,
}: {
  target: QualificationRecord;
  onClose: () => void;
  onChanged: () => void;
}) {
  const qualificationId = target.id;
  const [record, setRecord] = useState<QualificationRecord>(target);
  const [versions, setVersions] = useState<QualificationVersionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 重拉版本列表 + 权威 current_version（上传/回滚响应不含完整记录，指针状态以 GET 为准），
  // 并回调父级刷新主表 current_version
  const refresh = useCallback(async () => {
    try {
      const [versionsRes, recordRes] = await Promise.all([
        bidMaterialsApi.qualifications.versions(qualificationId),
        bidMaterialsApi.qualifications.get(qualificationId),
      ]);
      setVersions(versionsRes);
      setRecord(recordRes);
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载版本历史失败");
    } finally {
      setLoading(false);
    }
  }, [qualificationId, onChanged]);

  useEffect(() => {
    void refresh();
    // 首开拉取；refresh 身份由稳定回调保证，对话框生命周期内不变更
  }, [refresh]);

  const handleRollback = async (v: number) => {
    if (
      !window.confirm(
        `确认回滚到 v${v}？回滚=把当前版指针改到该版本，内容不变、不删除任何版本。`,
      )
    )
      return;
    try {
      await bidMaterialsApi.qualifications.rollback(qualificationId, v);
      toast.success(`已回滚到 v${v}（当前版指针已更新）`);
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "回滚失败");
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error("请先选择要上传的文件（PNG/JPG，≤20MB）");
      return;
    }
    setUploading(true);
    try {
      const res = await bidMaterialsApi.qualifications.uploadVersion(
        qualificationId,
        file,
        note.trim() || undefined,
      );
      if (res.created) {
        toast.success(`已建版本 v${res.version}`);
      } else {
        toast.info(
          `内容与既有版本相同（sha256 去重），已返回既有版 v${res.version}`,
        );
      }
      setFile(null);
      setNote("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      await refresh();
    } catch (e) {
      // 后端守卫经此浮出：>20MB→413；非 png/jpg（magic byte）→400
      toast.error(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => (v ? undefined : onClose())}>
      <DialogContent className="sm:max-w-[720px]">
        <DialogHeader>
          <DialogTitle>
            版本历史 — {QUAL_TYPE_LABELS[record.qual_type] ?? record.qual_type}
            （{record.cert_no}）
          </DialogTitle>
          <DialogDescription>
            MinIO
            版本库：版本不可变只追加；回滚=把当前版指针改到目标版本，内容不变不删版。文件仅按当前版下发，预览/下载只挂当前版。
          </DialogDescription>
        </DialogHeader>

        <div className="grid max-h-[50vh] gap-3 overflow-y-auto py-1">
          {/* 版本列表 */}
          {loading && versions.length === 0 ? (
            <div className="text-muted-foreground flex items-center justify-center gap-2 py-10 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
            </div>
          ) : (
            <div className="border-border overflow-hidden rounded-xl border">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="bg-muted/50 text-muted-foreground border-border border-b text-left">
                      <th className="px-3 py-2 font-medium">版本</th>
                      <th className="px-3 py-2 font-medium">格式</th>
                      <th className="px-3 py-2 font-medium">大小</th>
                      <th className="px-3 py-2 font-medium">备注</th>
                      <th className="px-3 py-2 font-medium">上传时间</th>
                      <th className="px-3 py-2 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {versions.map((v) => {
                      const isCurrent = v.version === record.current_version;
                      return (
                        <tr
                          key={v.version}
                          className={cn(
                            "border-border border-b transition-colors last:border-b-0",
                            isCurrent && "bg-muted/30",
                          )}
                        >
                          <td className="px-3 py-2 whitespace-nowrap">
                            <div className="flex items-center gap-2">
                              <span className="text-foreground font-medium tabular-nums">
                                v{v.version}
                              </span>
                              {isCurrent && (
                                <Badge
                                  variant="outline"
                                  className="border-emerald-200 bg-emerald-50 text-emerald-700"
                                >
                                  当前
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="text-muted-foreground px-3 py-2 font-mono text-xs uppercase">
                            {v.file_ext || "—"}
                          </td>
                          <td className="text-muted-foreground px-3 py-2 whitespace-nowrap tabular-nums">
                            {formatFileSize(v.file_size)}
                          </td>
                          <td className="text-muted-foreground max-w-[200px] px-3 py-2">
                            <span
                              className="line-clamp-2"
                              title={v.note ?? undefined}
                            >
                              {v.note ?? "—"}
                            </span>
                          </td>
                          <td className="text-muted-foreground px-3 py-2 whitespace-nowrap">
                            {formatDateTime(v.uploaded_at)}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {isCurrent ? (
                              <Button asChild variant="outline" size="sm">
                                <a
                                  href={bidMaterialsApi.qualifications.fileUrl(
                                    qualificationId,
                                  )}
                                  target="_blank"
                                  rel="noreferrer"
                                  title="预览/下载当前版（cookie 认证随行）"
                                >
                                  预览/下载
                                </a>
                              </Button>
                            ) : (
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={uploading}
                                onClick={() => void handleRollback(v.version)}
                              >
                                回滚到此版
                              </Button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {versions.length === 0 && (
                      <tr>
                        <td
                          colSpan={6}
                          className="text-muted-foreground px-3 py-8 text-center"
                        >
                          还没有任何版本——请在下方上传 v1。
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 上传新版本 */}
          <div className="border-border grid gap-2 rounded-xl border p-3">
            <div className="text-foreground text-sm font-medium">
              上传新版本
            </div>
            <p className="text-muted-foreground text-xs">
              仅接受 PNG/JPG 图片，≤20MB；内容重复时按 sha256
              去重，幂等返回既有版本。
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg"
                className="max-w-[280px]"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <Input
                value={note}
                maxLength={200}
                placeholder="版本备注（≤200 字，可选）"
                className="w-56"
                onChange={(e) => setNote(e.target.value)}
              />
              <Button
                size="sm"
                disabled={uploading || !file}
                onClick={() => void handleUpload()}
              >
                {uploading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                上传
              </Button>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
