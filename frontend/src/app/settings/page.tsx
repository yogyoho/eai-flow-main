"use client";

import { Loader2 } from "lucide-react";
import { Suspense, useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { DataSourceManager } from "@/extensions/data-source/DataSourceManager";
import PluginMarketplace from "@/extensions/plugin/PluginMarketplace";
import { useI18n } from "@/core/i18n/hooks";

import { BasicSettings } from "./basic-settings";

export default function SettingsPage() {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState("basic");

  const tabs = [
    { id: "basic", label: t.settings.sections.basic },
    { id: "data-sources", label: "数据源" },
    { id: "plugins", label: "插件" },
  ];

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="bg-background border-b border-border h-16 flex items-center px-6 shrink-0">
        <h1 className="font-bold text-lg tracking-tight text-foreground">{t.settings.basic.title}</h1>
      </header>

      {/* 左右布局：左侧导航 + 右侧内容 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧导航 */}
        <nav className="w-56 border-r border-border bg-muted/30 flex flex-col py-4 px-3 shrink-0">
          {tabs.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === id
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        {/* 右侧内容 */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === "basic" && (
            <div className="p-6">
              <div className="max-w-4xl mx-auto">
                <BasicSettings />
              </div>
            </div>
          )}
          {activeTab === "data-sources" && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                  <Loader2 className="h-8 w-8 animate-spin text-primary mr-2" />
                  加载中...
                </div>
              }
            >
              <DataSourceManager />
            </Suspense>
          )}
          {activeTab === "plugins" && (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                  加载中...
                </div>
              }
            >
              <PluginMarketplace />
            </Suspense>
          )}
        </div>
      </div>
      <Toaster />
    </div>
  );
}
