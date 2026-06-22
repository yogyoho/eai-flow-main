"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import {
  createDomain,
  deleteDomain,
  fetchDomains,
  updateDomain,
  type DomainResponse,
} from "@/extensions/app-center/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

import { TableSelect, type TableSelectOption } from "./controls";

/** accent → 实心色块背景类（用于下拉项的色点） */
const ACCENT_SWATCH: Record<string, string> = {
  blue: "bg-blue-500",
  violet: "bg-violet-500",
  cyan: "bg-cyan-500",
  amber: "bg-amber-500",
  emerald: "bg-emerald-500",
  rose: "bg-rose-500",
  indigo: "bg-indigo-500",
  teal: "bg-teal-500",
  orange: "bg-orange-500",
  sky: "bg-sky-500",
  slate: "bg-slate-500",
};

const ACCENT_OPTIONS = [
  "blue", "violet", "cyan", "amber", "emerald",
  "rose", "indigo", "teal", "orange", "sky", "slate",
];

const ACCENT_SELECT_OPTIONS: TableSelectOption[] = ACCENT_OPTIONS.map((c) => ({
  value: c,
  label: c,
  swatch: ACCENT_SWATCH[c],
}));

export function DomainManagement() {
  const [domains, setDomains] = useState<DomainResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  // 新建域表单
  const [showForm, setShowForm] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newAccent, setNewAccent] = useState("blue");
  const [newUniversal, setNewUniversal] = useState(false);

  async function load() {
    setIsLoading(true);
    try {
      setDomains(await fetchDomains());
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate() {
    if (!newKey.trim() || !newLabel.trim()) return;
    setSaving("__new__");
    try {
      await createDomain({
        key: newKey.trim(),
        label: newLabel.trim(),
        accentColor: newAccent,
        isUniversal: newUniversal,
      });
      setShowForm(false);
      setNewKey("");
      setNewLabel("");
      setNewAccent("blue");
      setNewUniversal(false);
      await load();
    } finally {
      setSaving(null);
    }
  }

  async function handleUpdate(
    key: string,
    patch: Partial<DomainResponse>,
  ) {
    setSaving(key);
    try {
      await updateDomain(key, {
        label: patch.label,
        accentColor: patch.accentColor,
        sortOrder: patch.sortOrder,
        isUniversal: patch.isUniversal,
      });
      await load();
    } finally {
      setSaving(null);
    }
  }

  async function handleDelete(key: string, label: string) {
    if (!confirm(`确认删除业务域「${label}」？该域下的应用需先迁移至其他域。`)) return;
    setSaving(key);
    try {
      await deleteDomain(key);
      await load();
    } catch {
      alert("删除失败：该业务域下仍有应用，请先迁移应用后再删除。");
    } finally {
      setSaving(null);
    }
  }

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">业务域分类</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            通用域固定置顶；业务域按 sortOrder 排序。
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setShowForm((v) => !v)}>
          <Plus className="size-4 mr-1" /> 新增业务域
        </Button>
      </div>

      {showForm && (
        <div className="mb-4 rounded-lg border border-dashed border-border bg-muted/30 p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-muted-foreground">Key（唯一标识）</label>
              <Input
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="如：合规审查"
                className="mt-1 h-9"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">显示名称</label>
              <Input
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder="如：合规审查"
                className="mt-1 h-9"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">强调色</label>
              <div className="mt-1">
                <TableSelect
                  value={newAccent}
                  options={ACCENT_SELECT_OPTIONS}
                  onChange={setNewAccent}
                />
              </div>
            </div>
            <div className="flex items-end gap-3">
              <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
                <Switch
                  checked={newUniversal}
                  onCheckedChange={setNewUniversal}
                />
                通用域
              </label>
              <Button size="sm" onClick={handleCreate} disabled={saving === "__new__"}>
                {saving === "__new__" ? <Loader2 className="size-4 animate-spin" /> : "创建"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">Key</th>
                <th className="px-4 py-2.5 text-left font-medium">显示名称</th>
                <th className="px-4 py-2.5 text-left font-medium">强调色</th>
                <th className="px-4 py-2.5 text-left font-medium">排序</th>
                <th className="px-4 py-2.5 text-left font-medium">通用域</th>
                <th className="px-4 py-2.5 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {domains.map((d) => (
                <tr key={d.key} className="hover:bg-muted/20">
                  <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{d.key}</td>
                  <td className="px-4 py-2">
                    <InlineText
                      value={d.label}
                      onSave={(v) => handleUpdate(d.key, { label: v })}
                      disabled={saving === d.key}
                    />
                  </td>
                  <td className="px-4 py-2">
                    <TableSelect
                      value={d.accentColor}
                      options={ACCENT_SELECT_OPTIONS}
                      onChange={(v) => handleUpdate(d.key, { accentColor: v })}
                      disabled={saving === d.key}
                    />
                  </td>
                  <td className="px-4 py-2">
                    <Input
                      type="number"
                      defaultValue={d.sortOrder}
                      onBlur={(e) => {
                        const v = parseInt(e.target.value, 10);
                        if (!Number.isNaN(v) && v !== d.sortOrder) {
                          handleUpdate(d.key, { sortOrder: v });
                        }
                      }}
                      className="h-8 w-16 shadow-none bg-muted/40 border-transparent text-center"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <Switch
                      checked={d.isUniversal}
                      onCheckedChange={(v) => handleUpdate(d.key, { isUniversal: v })}
                      disabled={saving === d.key}
                    />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleDelete(d.key, d.label)}
                      disabled={saving === d.key}
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

/** 行内可编辑文本：点击进入编辑，失焦保存。 */
function InlineText({
  value,
  onSave,
  disabled,
}: {
  value: string;
  onSave: (v: string) => void;
  disabled?: boolean;
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
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          setEditing(false);
          if (draft.trim() && draft.trim() !== value) onSave(draft.trim());
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setDraft(value);
            setEditing(false);
          }
        }}
        className="h-8 w-40"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      title={value}
      className="block w-40 truncate rounded px-1.5 py-0.5 text-left hover:bg-accent transition-colors"
    >
      {value}
    </button>
  );
}
