"use client";

import { Loader2, Settings } from "lucide-react";
import { Suspense, useEffect, useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { useI18n } from "@/core/i18n/hooks";
import { DataSourceManager } from "@/extensions/data-source/DataSourceManager";
import LicensePage from "@/extensions/license/LicensePage";


import { BasicSettings } from "./basic-settings";
import { usePermission } from "@/core/permissions";

export default function SettingsPage() {
  const { t } = useI18n();
  const { canPage } = usePermission();
  const [activeTab, setActiveTab] = useState("basic");

  const tabs = [
    { id: "basic", label: t.settings.sections.basic, pageId: "settings:page:general" },
    { id: "data-sources", label: "数据源", pageId: "settings:page:datasource" },
    { id: "license", label: "许可证", pageId: "settings:page:license" },
  ].filter(tab => canPage(tab.pageId));

  // 如果当前 activeTab 不在权限范围内，回退到第一个可见 tab
  useEffect(() => {
    const validIds = tabs.map(t => t.id);
    if (validIds.length > 0 && !validIds.includes(activeTab)) {
      setActiveTab(validIds[0]!);
    }
  }, [tabs, activeTab]);

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="bg-background border-b border-border h-16 flex items-center px-6 shrink-0">
        <div className="p-1 border rounded-sm bg-slate-50 border-slate-200 text-slate-600 shrink-0 mr-3">
          <Settings className="w-4 h-4" />
        </div>
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
          {activeTab === "license" && (
            <div className="p-6">
              <div className="max-w-4xl mx-auto">
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
