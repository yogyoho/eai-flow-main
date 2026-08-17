"use client";

import { Loader2, Settings } from "lucide-react";
import { Suspense, useEffect, useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { useI18n } from "@/core/i18n/hooks";
import { usePermission } from "@/core/permissions";
import { DataSourceManager } from "@/extensions/data-source/DataSourceManager";
import LicensePage from "@/extensions/license/LicensePage";

import { BasicSettings } from "./basic-settings";

export default function SettingsPage() {
  const { t } = useI18n();
  const { canPage } = usePermission();
  const [activeTab, setActiveTab] = useState("basic");

  const tabs = [
    {
      id: "basic",
      label: t.settings.sections.basic,
      pageId: "settings:page:general",
    },
    { id: "data-sources", label: "数据源", pageId: "settings:page:datasource" },
    { id: "license", label: "许可证", pageId: "settings:page:license" },
  ].filter((tab) => canPage(tab.pageId));

  // 如果当前 activeTab 不在权限范围内，回退到第一个可见 tab
  useEffect(() => {
    const validIds = tabs.map((t) => t.id);
    if (validIds.length > 0 && !validIds.includes(activeTab)) {
      setActiveTab(validIds[0]!);
    }
  }, [tabs, activeTab]);

  return (
    <div className="bg-background flex h-full flex-col">
      {/* Header */}
      <header className="bg-background border-border flex h-16 shrink-0 items-center border-b px-6">
        <div className="mr-3 shrink-0 rounded-sm border border-slate-200 bg-slate-50 p-1 text-slate-600">
          <Settings className="h-4 w-4" />
        </div>
        <h1 className="text-foreground text-lg font-bold tracking-tight">
          {t.settings.basic.title}
        </h1>
      </header>

      {/* 左右布局：左侧导航 + 右侧内容 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧导航 */}
        <nav className="border-border bg-muted/30 flex w-56 shrink-0 flex-col border-r px-3 py-4">
          {tabs.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
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
              <div className="mx-auto max-w-4xl">
                <BasicSettings />
              </div>
            </div>
          )}
          {activeTab === "data-sources" && (
            <Suspense
              fallback={
                <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
                  <Loader2 className="text-primary mr-2 h-8 w-8 animate-spin" />
                  加载中...
                </div>
              }
            >
              <DataSourceManager />
            </Suspense>
          )}
          {activeTab === "license" && (
            <div className="p-6">
              <div className="mx-auto max-w-4xl">
                <LicensePage />
              </div>
            </div>
          )}
        </div>
      </div>
      <Toaster />
    </div>
  );
}
