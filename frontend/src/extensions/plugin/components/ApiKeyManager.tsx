"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  Copy,
  Trash2,
  AlertTriangle,
  Key,
  Loader2,
  X,
  Clock,
} from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { pluginApi } from "@/extensions/plugin/api";
import type { ApiKey, CreateApiKeyRequest } from "@/extensions/plugin/types";
import { cn } from "@/lib/utils";

const SCOPE_OPTIONS: { value: string; label: string }[] = [
  { value: "read", label: "读取" },
  { value: "write", label: "写入" },
  { value: "admin", label: "管理" },
  { value: "execute", label: "执行" },
];

function formatDate(dateString: string | null) {
  if (!dateString) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateString));
}

function isExpired(expiresAt: string | null) {
  if (!expiresAt) return false;
  return new Date(expiresAt) < new Date();
}

function maskKey(keyPrefix: string) {
  if (!keyPrefix) return "sk-***";
  return keyPrefix;
}

export function ApiKeyManager() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);

  // Create dialog
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateApiKeyRequest>({
    name: "",
    scope: [],
  });
  const [createLoading, setCreateLoading] = useState(false);
  const [createdKey, setCreatedKey] = useState<{ id: string; key: string } | null>(null);

  // Revoke confirm
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const [revoking, setRevoking] = useState(false);

  const loadKeys = useCallback(async () => {
    try {
      const data = await pluginApi.listApiKeys();
      setKeys(data);
    } catch {
      toast.error("加载密钥列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  const handleCreate = async () => {
    if (!createForm.name.trim()) return;
    if (createForm.scope.length === 0) {
      toast.error("请至少选择一个权限范围");
      return;
    }
    setCreateLoading(true);
    try {
      const result = await pluginApi.createApiKey(createForm);
      setCreatedKey(result);
      setKeys((prev) => [
        {
          id: result.id,
          name: createForm.name,
          keyPrefix: result.key.slice(0, 8) + "...",
          scope: createForm.scope,
          projectId: createForm.projectId ?? null,
          createdBy: "",
          expiresAt: createForm.expiresAt ?? null,
          lastUsedAt: null,
          createdAt: new Date().toISOString(),
        },
        ...prev,
      ]);
      toast.success("密钥创建成功");
    } catch {
      toast.error("创建密钥失败");
    } finally {
      setCreateLoading(false);
    }
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    setRevoking(true);
    try {
      await pluginApi.revokeApiKey(revokeTarget);
      setKeys((prev) => prev.filter((k) => k.id !== revokeTarget));
      toast.success("密钥已撤销");
    } catch {
      toast.error("撤销密钥失败");
    } finally {
      setRevoking(false);
      setRevokeTarget(null);
    }
  };

  const toggleScope = (scope: string) => {
    setCreateForm((prev) => ({
      ...prev,
      scope: prev.scope.includes(scope)
        ? prev.scope.filter((s) => s !== scope)
        : [...prev.scope, scope],
    }));
  };

  const closeCreateDialog = () => {
    setShowCreate(false);
    setCreateForm({ name: "", scope: [] });
    setCreatedKey(null);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">API 密钥</h2>
          <p className="text-sm text-muted-foreground">管理用于外部访问的 API 密钥</p>
        </div>
        <Button onClick={() => setShowCreate(true)} size="sm">
          <Plus className="mr-1.5 h-4 w-4" />
          创建密钥
        </Button>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : keys.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Key className="mb-3 h-10 w-10 text-muted-foreground/50" />
            <p className="text-sm font-medium">暂无 API 密钥</p>
            <p className="mt-1 text-xs">点击"创建密钥"按钮生成新的访问密钥</p>
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 z-10 bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-6 py-3 font-medium">名称</th>
                <th className="px-4 py-3 font-medium">密钥</th>
                <th className="px-4 py-3 font-medium">权限范围</th>
                <th className="px-4 py-3 font-medium">过期时间</th>
                <th className="px-4 py-3 font-medium">最后使用</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {keys.map((key) => {
                const expired = isExpired(key.expiresAt);
                return (
                  <tr
                    key={key.id}
                    className={cn(
                      "transition-colors hover:bg-muted/50",
                      expired && "opacity-50",
                    )}
                  >
                    <td className="px-6 py-3">
                      <span className="font-medium text-foreground">{key.name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <code className="rounded bg-muted px-2 py-0.5 text-xs font-mono text-muted-foreground">
                        {maskKey(key.keyPrefix)}
                      </code>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {key.scope.map((s) => (
                          <Badge key={s} variant="secondary" className="text-xs">
                            {s}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "text-xs",
                          expired
                            ? "text-destructive"
                            : "text-muted-foreground",
                        )}
                      >
                        {expired ? "已过期" : formatDate(key.expiresAt)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {formatDate(key.lastUsedAt)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setRevokeTarget(key.id)}
                        className="h-7 text-xs text-destructive hover:text-destructive hover:bg-destructive/10"
                      >
                        <Trash2 className="mr-1 h-3 w-3" />
                        撤销
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Create Dialog */}
      <AnimatePresence>
        {showCreate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={closeCreateDialog}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-md overflow-hidden rounded-2xl bg-background shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-border px-6 py-4">
                <h3 className="text-lg font-semibold text-foreground">
                  {createdKey ? "密钥创建成功" : "创建 API 密钥"}
                </h3>
                <Button variant="ghost" size="icon" onClick={closeCreateDialog}>
                  <X className="h-5 w-5" />
                </Button>
              </div>

              {createdKey ? (
                <div className="p-6">
                  <div className="rounded-lg border border-warning/20 bg-warning/5 p-4 mb-4">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="h-5 w-5 shrink-0 text-warning mt-0.5" />
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          请立即保存，此密钥仅显示一次
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          关闭此窗口后将无法再次查看完整密钥
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="rounded-lg bg-muted p-4">
                    <div className="mb-2 text-xs font-medium text-muted-foreground">
                      密钥
                    </div>
                    <code className="block break-all rounded bg-background p-3 text-sm font-mono text-foreground">
                      {createdKey.key}
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3 w-full"
                      onClick={() => {
                        navigator.clipboard.writeText(createdKey.key);
                        toast.success("密钥已复制到剪贴板");
                      }}
                    >
                      <Copy className="mr-1.5 h-3.5 w-3.5" />
                      复制密钥
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-5 p-6">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-foreground">
                      密钥名称 <span className="text-destructive">*</span>
                    </label>
                    <Input
                      type="text"
                      value={createForm.name}
                      onChange={(e) =>
                        setCreateForm({ ...createForm, name: e.target.value })
                      }
                      placeholder="例如：生产环境访问"
                      className="w-full"
                    />
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-foreground">
                      权限范围 <span className="text-destructive">*</span>
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {SCOPE_OPTIONS.map((opt) => {
                        const checked = createForm.scope.includes(opt.value);
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => toggleScope(opt.value)}
                            className={cn(
                              "rounded-lg border px-3 py-2 text-sm transition-colors",
                              checked
                                ? "border-primary bg-primary/10 text-primary font-medium"
                                : "border-border text-muted-foreground hover:bg-muted",
                            )}
                          >
                            {opt.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-sm font-medium text-foreground">
                      过期时间（可选）
                    </label>
                    <Input
                      type="date"
                      value={createForm.expiresAt ?? ""}
                      onChange={(e) =>
                        setCreateForm({
                          ...createForm,
                          expiresAt: e.target.value || undefined,
                        })
                      }
                      className="w-full"
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
                <Button variant="outline" onClick={closeCreateDialog}>
                  {createdKey ? "关闭" : "取消"}
                </Button>
                {!createdKey && (
                  <Button
                    onClick={handleCreate}
                    disabled={!createForm.name.trim() || createLoading}
                  >
                    {createLoading && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                    创建
                  </Button>
                )}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Revoke Confirm Dialog */}
      <AnimatePresence>
        {revokeTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
              onClick={() => setRevokeTarget(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-sm overflow-hidden rounded-2xl bg-background shadow-xl"
            >
              <div className="p-6 text-center">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                  <AlertTriangle className="h-6 w-6 text-destructive" />
                </div>
                <h3 className="text-lg font-semibold text-foreground">
                  确认撤销密钥
                </h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  撤销后使用该密钥的所有访问将立即失效，此操作不可撤销。
                </p>
              </div>
              <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
                <Button variant="outline" onClick={() => setRevokeTarget(null)}>
                  取消
                </Button>
                <Button
                  variant="destructive"
                  onClick={handleRevoke}
                  disabled={revoking}
                >
                  {revoking && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                  确认撤销
                </Button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
