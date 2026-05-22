"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  Loader2,
  Plus,
  X,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { dataSourceApi } from "./api";
import { DataSourceForm } from "./components/DataSourceForm";
import type { CreateDataSourceRequest, DataSource } from "./types";

import { DataSourceCard } from "./components/DataSourceCard";

// ─── Toast ─────────────────────────────────────────────────────────────────────

type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

function ToastContainer({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed right-6 bottom-6 z-[100] flex flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: 16, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className={cn(
              "pointer-events-auto flex items-center gap-3 rounded-xl border px-4 py-3 text-sm font-medium shadow-lg backdrop-blur-sm",
              t.type === "success" && "border-green-200 bg-green-600 text-white",
              t.type === "error" && "border-red-200 bg-red-600 text-white",
              t.type === "info" && "border-blue-200 bg-blue-600 text-white",
            )}
          >
            {t.type === "success" && <CheckCircle2 className="h-4 w-4 shrink-0" />}
            {t.type === "error" && <AlertCircle className="h-4 w-4 shrink-0" />}
            {t.type === "info" && <Loader2 className="h-4 w-4 shrink-0" />}
            <span>{t.message}</span>
            <button onClick={() => onRemove(t.id)} className="ml-1 opacity-60 transition-opacity hover:opacity-100">
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const show = useCallback((message: string, type: ToastType = "info") => {
    const id = ++counter.current;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);
  const remove = useCallback((id: number) => setToasts((prev) => prev.filter((t) => t.id !== id)), []);
  return { toasts, show, remove };
}

// ─── DataSourceManager ────────────────────────────────────────────────────────

export function DataSourceManager() {
  const { toasts, show: toast, remove: removeToast } = useToast();
  const [sources, setSources] = useState<DataSource[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [testingIds, setTestingIds] = useState<Set<string>>(new Set());
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
  const [showForm, setShowForm] = useState(false);
  const [editingSource, setEditingSource] = useState<DataSource | null>(null);
  const [formLoading, setFormLoading] = useState(false);

  const loadSources = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await dataSourceApi.list();
      setSources(data);
    } catch (e: any) {
      toast(e?.message ?? "加载数据源失败", "error");
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  // ── CRUD handlers ──

  const handleCreate = async (data: CreateDataSourceRequest) => {
    setFormLoading(true);
    try {
      await dataSourceApi.create(data);
      setShowForm(false);
      toast("数据源创建成功", "success");
      loadSources();
    } catch (e: any) {
      toast(e?.message ?? "创建失败", "error");
    } finally {
      setFormLoading(false);
    }
  };

  const handleUpdate = async (data: CreateDataSourceRequest) => {
    if (!editingSource) return;
    setFormLoading(true);
    try {
      await dataSourceApi.update(editingSource.id, data);
      setEditingSource(null);
      toast("数据源已更新", "success");
      loadSources();
    } catch (e: any) {
      toast(e?.message ?? "更新失败", "error");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定要删除该数据源吗？此操作不可恢复。")) return;
    try {
      await dataSourceApi.delete(id);
      setSources((prev) => prev.filter((s) => s.id !== id));
      toast("数据源已删除", "success");
    } catch (e: any) {
      toast(e?.message ?? "删除失败", "error");
    }
  };

  const handleTest = async (id: string) => {
    setTestingIds((prev) => new Set(prev).add(id));
    try {
      const result = await dataSourceApi.testConnection(id);
      if (result.success) {
        toast("连接测试成功", "success");
      } else {
        toast(`连接测试失败: ${result.message}`, "error");
      }
      // Refresh to get updated status
      loadSources();
    } catch (e: any) {
      toast(e?.message ?? "连接测试失败", "error");
    } finally {
      setTestingIds((prev) => {
        const s = new Set(prev);
        s.delete(id);
        return s;
      });
    }
  };

  const handleSync = async (id: string) => {
    setSyncingIds((prev) => new Set(prev).add(id));
    try {
      await dataSourceApi.sync(id);
      toast("数据同步已触发", "success");
      // Refresh to get updated lastSyncAt
      setTimeout(loadSources, 1500);
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

  const handleEdit = (source: DataSource) => {
    setEditingSource(source);
  };

  return (
    <main className="flex-1 overflow-y-auto bg-muted/50 p-8">
      <div className="mx-auto max-w-6xl space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              数据源管理
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              管理和监控各类数据源连接，支持数据库、API、文件和GIS数据。
            </p>
          </div>
          <Button onClick={() => setShowForm(true)}>
            <Plus className="h-4 w-4" />
            添加数据源
          </Button>
        </div>

        {/* Card Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-center text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            加载中...
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence>
              {sources.map((source) => (
                <DataSourceCard
                  key={source.id}
                  source={source}
                  onEdit={() => handleEdit(source)}
                  onDelete={() => handleDelete(source.id)}
                  onTest={() => handleTest(source.id)}
                  onSync={() => handleSync(source.id)}
                  testing={testingIds.has(source.id)}
                  syncing={syncingIds.has(source.id)}
                />
              ))}
            </AnimatePresence>

            {sources.length === 0 && (
              <div className="col-span-full rounded-xl border border-dashed border-border bg-background py-12 text-center">
                <Database className="mx-auto mb-3 h-12 w-12 text-muted-foreground/50" />
                <h3 className="text-sm font-medium text-foreground">
                  暂无数据源
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  点击上方按钮添加第一个数据源
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create Form Modal */}
      <DataSourceForm
        open={showForm}
        onClose={() => setShowForm(false)}
        onSubmit={handleCreate}
        loading={formLoading}
      />

      {/* Edit Form Modal */}
      <DataSourceForm
        open={!!editingSource}
        onClose={() => setEditingSource(null)}
        onSubmit={handleUpdate}
        initialData={editingSource ?? undefined}
        loading={formLoading}
      />

      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </main>
  );
}
