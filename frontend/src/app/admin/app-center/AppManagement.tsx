"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import {
  createApp,
  deleteApp,
  fetchAllApps,
  fetchDomains,
  updateApp,
  type AppResponse,
  type DomainResponse,
} from "@/extensions/app-center/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const STAGE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "—" },
  { value: "overview", label: "概览" },
  { value: "collect", label: "采集" },
  { value: "process", label: "加工" },
  { value: "collaborate", label: "协作" },
  { value: "output", label: "输出" },
  { value: "retrieve", label: "检索" },
  { value: "manage", label: "管理" },
];

export function AppManagement() {
  const [apps, setApps] = useState<AppResponse[]>([]);
  const [domains, setDomains] = useState<DomainResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [draft, setDraft] = useState({
    appId: "",
    name: "",
    description: "",
    iconName: "layout-dashboard",
    businessDomain: "",
    stageTag: "",
    path: "",
    licenseModule: "",
    sortKey: "",
  });

  async function load() {
    setIsLoading(true);
    try {
      const [a, d] = await Promise.all([fetchAllApps(), fetchDomains()]);
      setApps(a);
      setDomains(d);
      if (!draft.businessDomain && d.length > 0) {
        setDraft((prev) => ({ ...prev, businessDomain: d[0].key }));
      }
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleUpdate(
    appId: string,
    patch: Partial<AppResponse>,
  ) {
    setSaving(appId);
    try {
      await updateApp(appId, {
        name: patch.name,
        description: patch.description,
        iconName: patch.iconName,
        businessDomain: patch.businessDomain,
        stageTag: patch.stageTag,
        path: patch.path,
        licenseModule: patch.licenseModule,
        adminOnly: patch.adminOnly,
        isEnabled: patch.isEnabled,
        sortOrder: patch.sortOrder,
        sortKey: patch.sortKey,
      });
      await load();
    } finally {
      setSaving(null);
    }
  }

  async function handleCreate() {
    if (!draft.appId.trim() || !draft.name.trim() || !draft.path.trim()) return;
    setSaving("__new__");
    try {
      await createApp({
        appId: draft.appId.trim(),
        name: draft.name.trim(),
        description: draft.description.trim() || undefined,
        iconName: draft.iconName,
        businessDomain: draft.businessDomain,
        stageTag: draft.stageTag || undefined,
        path: draft.path.trim(),
        licenseModule: draft.licenseModule.trim() || undefined,
        sortKey: draft.sortKey.trim() || draft.appId.trim(),
        isEnabled: true,
      });
      setShowForm(false);
      setDraft({
        appId: "", name: "", description: "", iconName: "layout-dashboard",
        businessDomain: domains[0]?.key ?? "", stageTag: "", path: "", licenseModule: "", sortKey: "",
      });
      await load();
    } finally {
      setSaving(null);
    }
  }

  async function handleDelete(appId: string, name: string) {
    if (!confirm(`确认删除应用「${name}」？`)) return;
    setSaving(appId);
    try {
      await deleteApp(appId);
      await load();
    } finally {
      setSaving(null);
    }
  }

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">应用列表</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            点击单元格编辑；修改「业务域」即变更分类。禁用后对普通用户隐藏。
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setShowForm((v) => !v)}>
          <Plus className="size-4 mr-1" /> 新增应用
        </Button>
      </div>

      {showForm && (
        <div className="mb-4 rounded-lg border border-dashed border-border bg-muted/30 p-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            <FormField label="App ID" required>
              <Input value={draft.appId} onChange={(e) => setDraft({ ...draft, appId: e.target.value })} className="h-9" placeholder="如：custom-tool" />
            </FormField>
            <FormField label="名称" required>
              <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="h-9" placeholder="应用名称" />
            </FormField>
            <FormField label="路径" required>
              <Input value={draft.path} onChange={(e) => setDraft({ ...draft, path: e.target.value })} className="h-9" placeholder="/custom-tool" />
            </FormField>
            <FormField label="图标名">
              <Input value={draft.iconName} onChange={(e) => setDraft({ ...draft, iconName: e.target.value })} className="h-9" placeholder="layout-dashboard" />
            </FormField>
            <FormField label="业务域">
              <select
                value={draft.businessDomain}
                onChange={(e) => setDraft({ ...draft, businessDomain: e.target.value })}
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
              >
                {domains.map((d) => (
                  <option key={d.key} value={d.key}>{d.label}</option>
                ))}
              </select>
            </FormField>
            <FormField label="阶段标签">
              <select
                value={draft.stageTag}
                onChange={(e) => setDraft({ ...draft, stageTag: e.target.value })}
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
              >
                {STAGE_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </FormField>
            <FormField label="License 模块">
              <Input value={draft.licenseModule} onChange={(e) => setDraft({ ...draft, licenseModule: e.target.value })} className="h-9" placeholder="留空=无需授权" />
            </FormField>
            <FormField label="排序键(拼音)">
              <Input value={draft.sortKey} onChange={(e) => setDraft({ ...draft, sortKey: e.target.value })} className="h-9" placeholder="留空=用 App ID" />
            </FormField>
          </div>
          <FormField label="描述">
            <Input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} className="h-9" placeholder="一句话描述" />
          </FormField>
          <div className="flex justify-end">
            <Button size="sm" onClick={handleCreate} disabled={saving === "__new__"}>
              {saving === "__new__" ? <Loader2 className="size-4 animate-spin" /> : "创建"}
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2.5 text-left font-medium">App ID</th>
                <th className="px-3 py-2.5 text-left font-medium">名称</th>
                <th className="px-3 py-2.5 text-left font-medium">业务域</th>
                <th className="px-3 py-2.5 text-left font-medium">阶段</th>
                <th className="px-3 py-2.5 text-left font-medium">路径</th>
                <th className="px-3 py-2.5 text-left font-medium">授权</th>
                <th className="px-3 py-2.5 text-center font-medium">管理员</th>
                <th className="px-3 py-2.5 text-center font-medium">启用</th>
                <th className="px-3 py-2.5 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {apps.map((a) => (
                <tr key={a.appId} className={`hover:bg-muted/20 ${!a.isEnabled ? "opacity-50" : ""}`}>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">{a.appId}</td>
                  <td className="px-3 py-2">
                    <InlineInput
                      value={a.name}
                      disabled={saving === a.appId}
                      onSave={(v) => handleUpdate(a.appId, { name: v })}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={a.businessDomain}
                      onChange={(e) => handleUpdate(a.appId, { businessDomain: e.target.value })}
                      disabled={saving === a.appId}
                      className="h-8 rounded-md border border-border bg-background px-1.5 text-xs min-w-[90px]"
                    >
                      {domains.map((d) => (
                        <option key={d.key} value={d.key}>{d.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={a.stageTag ?? ""}
                      onChange={(e) => handleUpdate(a.appId, { stageTag: e.target.value || undefined })}
                      disabled={saving === a.appId}
                      className="h-8 rounded-md border border-border bg-background px-1.5 text-xs"
                    >
                      {STAGE_OPTIONS.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <InlineInput
                      value={a.path}
                      disabled={saving === a.appId}
                      onSave={(v) => handleUpdate(a.appId, { path: v })}
                      mono
                    />
                  </td>
                  <td className="px-3 py-2">
                    <InlineInput
                      value={a.licenseModule ?? ""}
                      placeholder="无"
                      disabled={saving === a.appId}
                      onSave={(v) => handleUpdate(a.appId, { licenseModule: v || undefined })}
                    />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={a.adminOnly}
                      onChange={(e) => handleUpdate(a.appId, { adminOnly: e.target.checked })}
                      disabled={saving === a.appId}
                      className="size-4"
                    />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={a.isEnabled}
                      onChange={(e) => handleUpdate(a.appId, { isEnabled: e.target.checked })}
                      disabled={saving === a.appId}
                      className="size-4"
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => handleDelete(a.appId, a.name)}
                      disabled={saving === a.appId}
                      className="inline-flex items-center justify-center size-8 rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors disabled:opacity-50"
                      title="删除"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function FormField({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="text-xs text-muted-foreground">
        {label}
        {required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function InlineInput({
  value,
  onSave,
  disabled,
  placeholder,
  mono,
}: {
  value: string;
  onSave: (v: string) => void;
  disabled?: boolean;
  placeholder?: string;
  mono?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  useEffect(() => setDraft(value), [value]);

  if (editing) {
    return (
      <Input
        autoFocus
        value={draft}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          setEditing(false);
          if (draft.trim() !== value) onSave(draft.trim());
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setDraft(value);
            setEditing(false);
          }
        }}
        className={`h-8 min-w-[80px] ${mono ? "font-mono text-xs" : ""}`}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className={`block max-w-[160px] truncate rounded px-1.5 py-0.5 text-left hover:bg-accent transition-colors ${mono ? "font-mono text-xs" : ""} ${!value ? "text-muted-foreground/50" : ""}`}
      title={value || placeholder}
    >
      {value || placeholder}
    </button>
  );
}
