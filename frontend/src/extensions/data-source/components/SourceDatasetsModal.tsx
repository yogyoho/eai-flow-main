"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Pencil, Table, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { datasetApi } from "../api";
import type { DataSource, DataSourceDataset } from "../types";

interface Props {
  source: DataSource;
  open: boolean;
  onClose: () => void;
}

export function SourceDatasetsModal({ source, open, onClose }: Props) {
  const [datasets, setDatasets] = useState<DataSourceDataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<DataSourceDataset | null>(null);
  const [label, setLabel] = useState("");
  const [tableName, setTableName] = useState("");
  const [description, setDescription] = useState("");
  const [defaultQuery, setDefaultQuery] = useState("");
  const [keyColumns, setKeyColumns] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      setDatasets(await datasetApi.list(source.id));
    } catch {
      toast.error("加载数据集失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const resetForm = () => {
    setEditing(null);
    setLabel("");
    setTableName("");
    setDescription("");
    setDefaultQuery("");
    setKeyColumns("");
  };

  const startEdit = (d: DataSourceDataset) => {
    setEditing(d);
    setLabel(d.label);
    setTableName(d.tableName);
    setDescription(d.description ?? "");
    setDefaultQuery(d.defaultQuery ?? "");
    setKeyColumns((d.keyColumns ?? []).join(", "));
  };

  const submit = async () => {
    if (!label.trim() || !tableName.trim()) {
      toast.error("业务标签和表名必填");
      return;
    }
    const req = {
      label: label.trim(),
      tableName: tableName.trim(),
      description: description.trim() || undefined,
      defaultQuery: defaultQuery.trim() || undefined,
      keyColumns: keyColumns
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    setSaving(true);
    try {
      if (editing) {
        await datasetApi.update(editing.id, req);
        toast.success("数据集已更新");
      } else {
        await datasetApi.create(source.id, req);
        toast.success("数据集已添加");
      }
      resetForm();
      await load();
    } catch {
      toast.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (d: DataSourceDataset) => {
    if (!confirm(`删除数据集「${d.label}」?`)) return;
    try {
      await datasetApi.delete(d.id);
      setDatasets((prev) => prev.filter((x) => x.id !== d.id));
      if (editing?.id === d.id) {
        resetForm();
      }
      toast.success("已删除");
    } catch {
      toast.error("删除失败");
    }
  };

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="bg-background relative flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl shadow-xl"
          >
            <div className="border-border bg-muted/50 flex items-center justify-between border-b px-6 py-4">
              <div className="flex items-center gap-2">
                <Table className="text-primary h-5 w-5" />
                <div>
                  <h3 className="text-foreground text-lg font-semibold">
                    {source.name} · 业务数据集
                  </h3>
                  <p className="text-muted-foreground text-xs">
                    标注关键业务表,AI 按业务名直查
                  </p>
                </div>
              </div>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex-1 space-y-6 overflow-y-auto p-6">
              <div className="border-border space-y-3 rounded-xl border p-4">
                <div className="text-foreground text-sm font-medium">
                  {editing ? "编辑数据集" : "添加数据集"}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-muted-foreground mb-1 block text-xs">
                      业务标签 *
                    </label>
                    <Input
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                      placeholder="如:厂界噪声"
                    />
                  </div>
                  <div>
                    <label className="text-muted-foreground mb-1 block text-xs">
                      表名 *
                    </label>
                    <Input
                      value={tableName}
                      onChange={(e) => setTableName(e.target.value)}
                      placeholder="如:noise_monitor"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-muted-foreground mb-1 block text-xs">
                    描述(给 AI)
                  </label>
                  <Input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="如:厂界噪声 2024 年监测值"
                  />
                </div>
                <div>
                  <label className="text-muted-foreground mb-1 block text-xs">
                    关键列(逗号分隔)
                  </label>
                  <Input
                    value={keyColumns}
                    onChange={(e) => setKeyColumns(e.target.value)}
                    placeholder="如:点位, Leq, 时间"
                  />
                </div>
                <div>
                  <label className="text-muted-foreground mb-1 block text-xs">
                    默认查询 SQL(只读,Agent 按标签取数时执行)
                  </label>
                  <textarea
                    value={defaultQuery}
                    onChange={(e) => setDefaultQuery(e.target.value)}
                    rows={2}
                    placeholder="如:SELECT 点位, Leq FROM noise_monitor ORDER BY 时间 DESC LIMIT 100"
                    className="border-input bg-background focus-visible:ring-ring w-full resize-none rounded-lg border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
                  />
                </div>
                <div className="flex justify-end gap-2">
                  {editing && (
                    <Button variant="outline" size="sm" onClick={resetForm}>
                      取消编辑
                    </Button>
                  )}
                  <Button size="sm" onClick={submit} disabled={saving}>
                    {saving && (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    )}
                    {editing ? "保存修改" : "添加"}
                  </Button>
                </div>
              </div>

              <div>
                <div className="text-foreground mb-2 text-sm font-medium">
                  已有数据集({datasets.length})
                </div>
                {loading ? (
                  <div className="flex justify-center py-6">
                    <Loader2 className="text-muted-foreground h-5 w-5 animate-spin" />
                  </div>
                ) : datasets.length === 0 ? (
                  <div className="border-border text-muted-foreground rounded-lg border border-dashed py-6 text-center text-sm">
                    暂无数据集,用上方表单添加第一个
                  </div>
                ) : (
                  <div className="space-y-2">
                    {datasets.map((d) => (
                      <div
                        key={d.id}
                        className="border-border flex items-start justify-between gap-2 rounded-lg border p-3"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-foreground font-medium">
                              {d.label}
                            </span>
                            <span className="text-muted-foreground text-xs">
                              · {d.tableName}
                            </span>
                          </div>
                          {d.description && (
                            <p className="text-muted-foreground mt-0.5 truncate text-xs">
                              {d.description}
                            </p>
                          )}
                          {d.defaultQuery && (
                            <p className="text-muted-foreground/70 mt-0.5 truncate font-mono text-[11px]">
                              {d.defaultQuery}
                            </p>
                          )}
                        </div>
                        <div className="flex shrink-0 gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-muted-foreground hover:text-primary hover:bg-primary/10 h-7 w-7"
                            onClick={() => startEdit(d)}
                            title="编辑"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive h-7 w-7"
                            onClick={() => remove(d)}
                            title="删除"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
