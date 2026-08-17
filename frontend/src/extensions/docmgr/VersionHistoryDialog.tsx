"use client";

// EAI-CUSTOM (C10): 个人文档版本历史对话框 —— 列表 + 恢复。AI 反复改稿后可回退。
// 样式对齐 ExportDocxDialog 的自定义 modal（AnimatePresence + motion）。

import { AnimatePresence, motion } from "framer-motion";
import { History, Loader2, RotateCcw, Save, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

import { docmgrApi } from "../api";

interface VersionItem {
  id: string;
  label: string | null;
  created_at: string;
  preview: string;
  content_length: number;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

interface VersionHistoryDialogProps {
  threadId: string;
  relPath: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 恢复成功后回调（内容已写回 outputs 文件），宿主用它重载编辑器。 */
  onRestored: (content: string) => void;
  /** 取当前编辑器内容，供「保存当前版本」。 */
  getCurrentContent: () => Promise<string>;
}

export function VersionHistoryDialog({
  threadId,
  relPath,
  open,
  onOpenChange,
  onRestored,
  getCurrentContent,
}: VersionHistoryDialogProps) {
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const saveCurrent = async () => {
    setSaving(true);
    setError(null);
    try {
      const content = await getCurrentContent();
      await docmgrApi.createPersonalVersion(threadId, {
        rel_path: relPath,
        content,
        label: "手动保存",
      });
      await load();
    } catch (e) {
      setError(getErrorMessage(e, "保存版本失败"));
    } finally {
      setSaving(false);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await docmgrApi.listPersonalVersions(threadId, relPath);
      setVersions(res.versions);
    } catch (e) {
      setError(getErrorMessage(e, "加载版本失败"));
    } finally {
      setLoading(false);
    }
  }, [threadId, relPath]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const handleRestore = async (v: VersionItem) => {
    if (!window.confirm("恢复该版本将覆盖当前文档内容，确定继续？")) return;
    setRestoring(v.id);
    setError(null);
    try {
      const res = await docmgrApi.restorePersonalVersion(v.id);
      onRestored(res.content);
      onOpenChange(false);
    } catch (e) {
      setError(getErrorMessage(e, "恢复失败"));
    } finally {
      setRestoring(null);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={(e) => e.target === e.currentTarget && onOpenChange(false)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="bg-background border-border/60 flex max-h-[70vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border shadow-2xl"
          >
            {/* Header */}
            <div className="border-border/60 flex shrink-0 items-center justify-between border-b px-5 py-3.5">
              <div className="flex items-center gap-2.5">
                <div className="bg-primary/10 flex h-8 w-8 items-center justify-center rounded-xl">
                  <History className="text-primary h-4 w-4" />
                </div>
                <h2 className="text-foreground text-sm font-semibold">
                  版本历史
                </h2>
              </div>
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="text-muted-foreground hover:bg-muted hover:text-foreground flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Body */}
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground text-xs">
                  每文件保留最近 {20} 条，AI 编辑前自动快照。
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 shrink-0 text-xs"
                  disabled={saving}
                  onClick={saveCurrent}
                >
                  {saving ? (
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <Save className="mr-1 h-3 w-3" />
                  )}
                  保存当前版本
                </Button>
              </div>
              {error && (
                <div className="rounded-lg bg-red-50/30 px-3 py-2 text-xs text-red-600 dark:bg-red-950/10">
                  ⚠️ {error}
                </div>
              )}
              {loading ? (
                <div className="text-muted-foreground flex items-center justify-center py-10 text-sm">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  加载中...
                </div>
              ) : versions.length === 0 ? (
                <div className="text-muted-foreground py-10 text-center text-sm">
                  暂无版本。可在编辑器顶部点「保存版本」手动快照，AI
                  编辑前也会自动快照。
                </div>
              ) : (
                versions.map((v) => (
                  <div
                    key={v.id}
                    className="border-border rounded-lg border p-3 text-sm"
                  >
                    <div className="mb-1.5 flex items-center gap-2">
                      <span className="text-foreground truncate font-medium">
                        {v.label ?? "版本"}
                      </span>
                      <span className="text-muted-foreground ml-auto shrink-0 text-xs">
                        {new Date(v.created_at).toLocaleString("zh-CN")} ·{" "}
                        {v.content_length} 字符
                      </span>
                    </div>
                    <pre className="text-muted-foreground max-h-16 overflow-hidden text-xs leading-relaxed whitespace-pre-wrap">
                      {v.preview || "(空)"}
                    </pre>
                    <div className="mt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        disabled={restoring === v.id}
                        onClick={() => handleRestore(v)}
                      >
                        {restoring === v.id ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <RotateCcw className="mr-1 h-3 w-3" />
                        )}
                        恢复
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
