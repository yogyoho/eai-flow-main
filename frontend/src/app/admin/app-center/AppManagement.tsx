"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  createApp,
  deleteApp,
  fetchAllApps,
  fetchDomains,
  updateApp,
  type AppResponse,
  type DomainResponse,
} from "@/extensions/app-center/api";
import { getLicenseModules } from "@/extensions/license/api";
import { MODULE_LABELS } from "@/extensions/license/labels";

import { TableSelect, type TableSelectOption } from "./controls";

/** Radix Select 不允许空字符串 value，用 "none" 哨兵表示「无阶段标签」。 */
const NONE_STAGE = "none";

const STAGE_OPTIONS: TableSelectOption[] = [
  { value: NONE_STAGE, label: "无" },
  { value: "overview", label: "概览" },
  { value: "collect", label: "采集" },
  { value: "process", label: "加工" },
  { value: "collaborate", label: "协作" },
  { value: "output", label: "输出" },
  { value: "retrieve", label: "检索" },
  { value: "manage", label: "管理" },
];

export function AppManagement({ refreshKey = 0 }: { refreshKey?: number }) {
  const [apps, setApps] = useState<AppResponse[]>([]);
  const [domains, setDomains] = useState<DomainResponse[]>([]);
  const [licenseModules, setLicenseModules] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const licenseOptions: TableSelectOption[] = licenseModules.map((k) => ({
    value: k,
    label: MODULE_LABELS[k] ?? k,
  }));

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
      const [a, d, m] = await Promise.all([
        fetchAllApps(),
        fetchDomains(),
        getLicenseModules(),
      ]);
      setApps(a);
      setDomains(d);
      setLicenseModules(m);
      if (!draft.businessDomain && d.length > 0) {
        setDraft((prev) => ({ ...prev, businessDomain: d[0]?.key ?? "" }));
      }
      if (!draft.licenseModule && m.length > 0) {
        setDraft((prev) => ({ ...prev, licenseModule: m[0] ?? "" }));
      }
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  async function handleUpdate(appId: string, patch: Partial<AppResponse>) {
    setSaving(appId);
    try {
      await updateApp(appId, {
        name: patch.name,
        // EAI-CUSTOM: AppResponse 这三字段可空 (string|null)，AppUpdate 期望 string|undefined；null 视为「未提供」跳过
        description: patch.description ?? undefined,
        iconName: patch.iconName,
        businessDomain: patch.businessDomain,
        stageTag: patch.stageTag ?? undefined,
        path: patch.path,
        licenseModule: patch.licenseModule ?? undefined,
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
        licenseModule: draft.licenseModule,
        sortKey: draft.sortKey.trim() || draft.appId.trim(),
        isEnabled: true,
      });
      setShowForm(false);
      setDraft({
        appId: "",
        name: "",
        description: "",
        iconName: "layout-dashboard",
        businessDomain: domains[0]?.key ?? "",
        stageTag: "",
        path: "",
        licenseModule: licenseModules[0] ?? "",
        sortKey: "",
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
          <h2 className="text-foreground text-lg font-semibold">应用列表</h2>
          <p className="text-muted-foreground mt-0.5 text-xs">
            点击单元格编辑；修改「业务域」即变更分类。禁用后对普通用户隐藏。
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setShowForm((v) => !v)}
        >
          <Plus className="mr-1 size-4" /> 新增应用
        </Button>
      </div>

      {showForm && (
        <div className="border-border bg-muted/30 mb-4 space-y-3 rounded-lg border border-dashed p-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
            <FormField label="App ID" required>
              <Input
                value={draft.appId}
                onChange={(e) => setDraft({ ...draft, appId: e.target.value })}
                className="h-9"
                placeholder="如：custom-tool"
              />
            </FormField>
            <FormField label="名称" required>
              <Input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                className="h-9"
                placeholder="应用名称"
              />
            </FormField>
            <FormField label="路径" required>
              <Input
                value={draft.path}
                onChange={(e) => setDraft({ ...draft, path: e.target.value })}
                className="h-9"
                placeholder="/custom-tool"
              />
            </FormField>
            <FormField label="图标名">
              <Input
                value={draft.iconName}
                onChange={(e) =>
                  setDraft({ ...draft, iconName: e.target.value })
                }
                className="h-9"
                placeholder="layout-dashboard"
              />
            </FormField>
            <FormField label="业务域">
              <TableSelect
                value={draft.businessDomain}
                options={domains.map((d) => ({ value: d.key, label: d.label }))}
                onChange={(v) => setDraft({ ...draft, businessDomain: v })}
              />
            </FormField>
            <FormField label="阶段标签">
              <TableSelect
                value={draft.stageTag || NONE_STAGE}
                options={STAGE_OPTIONS}
                onChange={(v) =>
                  setDraft({ ...draft, stageTag: v === NONE_STAGE ? "" : v })
                }
              />
            </FormField>
            <FormField label="License 模块">
              <TableSelect
                value={draft.licenseModule}
                options={licenseOptions}
                onChange={(v) => setDraft({ ...draft, licenseModule: v })}
                placeholder="选择许可模块"
              />
            </FormField>
            <FormField label="排序键(拼音)">
              <Input
                value={draft.sortKey}
                onChange={(e) =>
                  setDraft({ ...draft, sortKey: e.target.value })
                }
                className="h-9"
                placeholder="留空=用 App ID"
              />
            </FormField>
          </div>
          <FormField label="描述">
            <Input
              value={draft.description}
              onChange={(e) =>
                setDraft({ ...draft, description: e.target.value })
              }
              className="h-9"
              placeholder="一句话描述"
            />
          </FormField>
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={handleCreate}
              disabled={saving === "__new__"}
            >
              {saving === "__new__" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                "创建"
              )}
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="text-muted-foreground size-6 animate-spin" />
        </div>
      ) : (
        <div className="border-border overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[900px] text-sm">
            <thead className="bg-muted/50 text-muted-foreground text-xs">
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
            <tbody className="divide-border divide-y">
              {apps.map((a) => (
                <tr
                  key={a.appId}
                  className={`hover:bg-muted/20 ${!a.isEnabled ? "opacity-50" : ""}`}
                >
                  <td className="text-muted-foreground px-3 py-2 font-mono text-xs whitespace-nowrap">
                    {a.appId}
                  </td>
                  <td className="px-3 py-2">
                    <InlineInput
                      value={a.name}
                      disabled={saving === a.appId}
                      onSave={(v) => handleUpdate(a.appId, { name: v })}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <TableSelect
                      value={a.businessDomain}
                      options={domains.map((d) => ({
                        value: d.key,
                        label: d.label,
                      }))}
                      onChange={(v) =>
                        handleUpdate(a.appId, { businessDomain: v })
                      }
                      disabled={saving === a.appId}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <TableSelect
                      value={a.stageTag ?? NONE_STAGE}
                      options={STAGE_OPTIONS}
                      onChange={(v) =>
                        handleUpdate(a.appId, {
                          stageTag: v === NONE_STAGE ? undefined : v,
                        })
                      }
                      disabled={saving === a.appId}
                    />
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
                    <TableSelect
                      value={a.licenseModule ?? ""}
                      options={licenseOptions}
                      onChange={(v) =>
                        handleUpdate(a.appId, { licenseModule: v })
                      }
                      disabled={saving === a.appId}
                      placeholder="选择许可模块"
                    />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <Switch
                      checked={a.adminOnly}
                      onCheckedChange={(v) =>
                        handleUpdate(a.appId, { adminOnly: v })
                      }
                      disabled={saving === a.appId}
                    />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <Switch
                      checked={a.isEnabled}
                      onCheckedChange={(v) =>
                        handleUpdate(a.appId, { isEnabled: v })
                      }
                      disabled={saving === a.appId}
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => handleDelete(a.appId, a.name)}
                      disabled={saving === a.appId}
                      className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive inline-flex size-8 items-center justify-center rounded-md transition-colors disabled:opacity-50"
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
      <label className="text-muted-foreground text-xs">
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
      className={`hover:bg-accent block max-w-[160px] truncate rounded px-1.5 py-0.5 text-left transition-colors ${mono ? "font-mono text-xs" : ""} ${!value ? "text-muted-foreground/50" : ""}`}
      title={value || placeholder}
    >
      {value || placeholder}
    </button>
  );
}
