"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Store,
  PackageCheck,
  Key,
  Settings,
  Power,
  PowerOff,
  Loader2,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { pluginApi } from "@/extensions/plugin/api";
import { ApiKeyManager } from "@/extensions/plugin/components/ApiKeyManager";
import { PluginCard } from "@/extensions/plugin/components/PluginCard";
import { PluginConfigForm } from "@/extensions/plugin/components/PluginConfigForm";
import type { Plugin, PluginInstance } from "@/extensions/plugin/types";
import { cn } from "@/lib/utils";

type TabId = "market" | "installed" | "apikeys";

const NAV_ITEMS: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: "market", label: "市场", icon: Store },
  { id: "installed", label: "已安装", icon: PackageCheck },
  { id: "apikeys", label: "API密钥", icon: Key },
];

function PluginMarketplaceContent() {
  const params = useSearchParams();
  const currentTab = (params.get("tab") ?? "market") as TabId;

  return (
    <div className="flex flex-col h-full bg-muted">
      {/* Tab Header */}
      <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
        <span className="font-bold text-lg tracking-tight text-foreground mr-8">
          插件市场
        </span>
        <nav className="flex items-center gap-6 text-sm font-medium text-muted-foreground h-full">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const href = `/plugins?tab=${id}`;
            const isActive = currentTab === id;
            return (
              <Link
                key={id}
                href={href}
                className={cn(
                  "flex items-center gap-2 h-full transition-colors py-5 border-b-2",
                  isActive
                    ? "text-primary border-primary"
                    : "border-transparent hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </header>

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden min-w-0 min-h-0 bg-background">
        <AnimatePresence mode="wait">
          {currentTab === "market" && (
            <motion.div
              key="market"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="h-full"
            >
              <MarketTab />
            </motion.div>
          )}
          {currentTab === "installed" && (
            <motion.div
              key="installed"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="h-full"
            >
              <InstalledTab />
            </motion.div>
          )}
          {currentTab === "apikeys" && (
            <motion.div
              key="apikeys"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.15 }}
              className="h-full"
            >
              <ApiKeyManager />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ─── Market Tab ────────────────────────────────────────────────────────────────

function MarketTab() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [installing, setInstalling] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [pluginList, instances] = await Promise.all([
        pluginApi.listPlugins(),
        pluginApi.listInstances(),
      ]);
      setPlugins(pluginList);
      setInstalledIds(new Set(instances.map((i) => i.pluginId)));
    } catch {
      toast.error("加载插件列表失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleInstall = async (pluginId: string) => {
    setInstalling(pluginId);
    try {
      await pluginApi.installPlugin(pluginId);
      setInstalledIds((prev) => new Set(prev).add(pluginId));
      toast.success("插件安装成功");
    } catch {
      toast.error("安装失败");
    } finally {
      setInstalling(null);
    }
  };

  const filteredPlugins = plugins.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.description.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-full">
      {/* Search Bar */}
      <div className="flex items-center gap-4 border-b border-border px-6 py-4">
        <div className="relative w-full max-w-sm">
          <Search className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder="搜索插件名称或描述..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-muted pl-9 pr-4"
          />
        </div>
        <span className="text-sm text-muted-foreground">
          共 {plugins.length} 个插件
        </span>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            加载中...
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence>
              {filteredPlugins.map((plugin) => (
                <motion.div
                  layout
                  key={plugin.id}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.2 }}
                >
                  <PluginCard
                    plugin={plugin}
                    installed={installedIds.has(plugin.id)}
                    onInstall={
                      installing === plugin.id
                        ? undefined
                        : () => handleInstall(plugin.id)
                    }
                  />
                  {installing === plugin.id && (
                    <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-background/60">
                      <Loader2 className="h-6 w-6 animate-spin text-primary" />
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>

            {filteredPlugins.length === 0 && (
              <div className="col-span-full flex flex-col items-center py-16 text-muted-foreground">
                <Store className="mb-3 h-10 w-10 text-muted-foreground/50" />
                <p className="text-sm font-medium">未找到匹配的插件</p>
                <p className="mt-1 text-xs">尝试调整搜索关键词</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Installed Tab ─────────────────────────────────────────────────────────────

function InstalledTab() {
  const [instances, setInstances] = useState<PluginInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [configureTarget, setConfigureTarget] = useState<PluginInstance | null>(null);

  const loadInstances = useCallback(async () => {
    try {
      const data = await pluginApi.listInstances();
      setInstances(data);
    } catch {
      toast.error("加载已安装插件失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInstances();
  }, [loadInstances]);

  const handleToggle = async (instance: PluginInstance) => {
    setTogglingId(instance.id);
    try {
      const enabled = instance.status === "disabled";
      await pluginApi.toggleInstance(instance.id, enabled);
      setInstances((prev) =>
        prev.map((i) =>
          i.id === instance.id
            ? { ...i, status: enabled ? "active" as const : "disabled" as const }
            : i,
        ),
      );
      toast.success(enabled ? "插件已启用" : "插件已禁用");
    } catch {
      toast.error("操作失败");
    } finally {
      setTogglingId(null);
    }
  };

  const handleConfigSave = async (config: Record<string, unknown>) => {
    if (!configureTarget) return;
    try {
      const updated = await pluginApi.updateInstance(configureTarget.id, config);
      setInstances((prev) =>
        prev.map((i) => (i.id === configureTarget.id ? updated : i)),
      );
      setConfigureTarget(null);
      toast.success("配置已保存");
    } catch {
      toast.error("保存配置失败");
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            加载中...
          </div>
        ) : instances.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <PackageCheck className="mb-3 h-10 w-10 text-muted-foreground/50" />
            <p className="text-sm font-medium">暂无已安装的插件</p>
            <p className="mt-1 text-xs">前往"市场"标签页安装插件</p>
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 z-10 bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-6 py-3 font-medium">插件名称</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">最后同步</th>
                <th className="px-4 py-3 font-medium">安装时间</th>
                <th className="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {instances.map((instance) => (
                <tr
                  key={instance.id}
                  className="transition-colors hover:bg-muted/50"
                >
                  <td className="px-6 py-3">
                    <span className="font-medium text-foreground">
                      {instance.pluginName}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-muted-foreground">
                      {instance.pluginType}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium",
                        instance.status === "active"
                          ? "border border-success/20 bg-success/10 text-success"
                          : instance.status === "error"
                            ? "border border-destructive/20 bg-destructive/10 text-destructive"
                            : "border border-border bg-muted text-muted-foreground",
                      )}
                    >
                      {instance.status === "active" ? "运行中" : instance.status === "error" ? "错误" : "已禁用"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {instance.lastSyncAt
                      ? new Date(instance.lastSyncAt).toLocaleDateString("zh-CN")
                      : "-"}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {new Date(instance.createdAt).toLocaleDateString("zh-CN")}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggle(instance)}
                        disabled={togglingId === instance.id}
                        className={cn(
                          "h-7 text-xs",
                          instance.status === "active"
                            ? "text-muted-foreground hover:text-warning hover:bg-warning/10"
                            : "text-muted-foreground hover:text-success hover:bg-success/10",
                        )}
                      >
                        {togglingId === instance.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : instance.status === "active" ? (
                          <>
                            <PowerOff className="mr-1 h-3.5 w-3.5" />
                            禁用
                          </>
                        ) : (
                          <>
                            <Power className="mr-1 h-3.5 w-3.5" />
                            启用
                          </>
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfigureTarget(instance)}
                        className="h-7 text-xs text-muted-foreground hover:text-primary hover:bg-primary/10"
                      >
                        <Settings className="mr-1 h-3.5 w-3.5" />
                        配置
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Configure Modal */}
      <AnimatePresence>
        {configureTarget && (
          <ConfigureModal
            instance={configureTarget}
            onClose={() => setConfigureTarget(null)}
            onSave={handleConfigSave}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Configure Modal ───────────────────────────────────────────────────────────

function ConfigureModal({
  instance,
  onClose,
  onSave,
}: {
  instance: PluginInstance;
  onClose: () => void;
  onSave: (config: Record<string, unknown>) => void;
}) {
  // We need to fetch the plugin to get configSchema; for now use instance config
  // In a real scenario, we'd look up the plugin schema from the registry
  const [config, setConfig] = useState<Record<string, unknown>>({ ...instance.config });
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await pluginApi.listPlugins();
        setPlugins(data);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const plugin = plugins.find((p) => p.id === instance.pluginId);
  const schema = plugin?.configSchema ?? { properties: {}, required: [] };

  return (
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
        className="relative w-full max-w-lg max-h-[85vh] flex flex-col overflow-hidden rounded-2xl bg-background shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h3 className="text-lg font-semibold text-foreground">
              配置插件
            </h3>
            <p className="text-sm text-muted-foreground">{instance.pluginName}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <span className="text-lg leading-none">&times;</span>
          </Button>
        </div>

        <div className="flex-1 overflow-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <PluginConfigForm
              schema={schema}
              values={config}
              onChange={setConfig}
            />
          )}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => onSave(config)}>保存</Button>
        </div>
      </motion.div>
    </div>
  );
}

export { PluginMarketplaceContent };

export default function PluginMarketplace() {
  return <PluginMarketplaceContent />;
}
