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
import { cn } from "@/lib/utils";

const ACCENT_OPTIONS = [
  "blue", "violet", "cyan", "amber", "emerald",
  "rose", "indigo", "teal", "orange", "sky", "slate",
];

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
              <select
                value={newAccent}
                onChange={(e) => setNewAccent(e.target.value)}
                className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
              >
                {ACCENT_OPTIONS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="flex items-end gap-3">
              <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={newUniversal}
                  onChange={(e) => setNewUniversal(e.target.checked)}
                  className="size-4"
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
                    <select
                      value={d.accentColor}
                      onChange={(e) => handleUpdate(d.key, { accentColor: e.target.value })}
                      disabled={saving === d.key}
                      className="h-8 rounded-md border border-border bg-background px-2 text-xs"
                    >
                      {ACCENT_OPTIONS.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
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
                      className="h-8 w-16"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input
                      type="checkbox"
                      checked={d.isUniversal}
                      onChange={(e) => handleUpdate(d.key, { isUniversal: e.target.checked })}
                      disabled={saving === d.key}
                      className="size-4"
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
        className={cn("h-8 min-w-[120px]")}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="rounded px-1.5 py-0.5 text-left hover:bg-accent transition-colors"
    >
      {value}
    </button>
  );
}
