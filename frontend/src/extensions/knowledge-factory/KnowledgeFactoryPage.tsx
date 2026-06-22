"use client";

import { Factory, LayoutDashboard } from "lucide-react";
import React, { useState } from "react";

import {
  SampleReports,
  TemplateExtraction,
  TemplateEditor,
  LawLibrary,
  RuleEngine,
  VersionControl,
  QualityAssessment,
  WebScraper,
  BusinessDictionary,
  TabNavigation,
} from "@/extensions/knowledge-factory/index";
import type { TabId } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";


export default function KnowledgeFactoryPage() {
  const [activeTab, setActiveTab] = useState<TabId>("reports");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const renderContent = () => {
    switch (activeTab) {
      case "reports":
        return <SampleReports />;
      case "extraction":
        return <TemplateExtraction />;
      case "editor":
        return <TemplateEditor />;
      case "law":
        return <LawLibrary />;
      case "rules":
        return <RuleEngine />;
      case "version":
        return <VersionControl />;
      case "quality":
        return <QualityAssessment />;
      case "scraper":
        return <WebScraper />;
      case "dictionaries":
        return <BusinessDictionary />;
      default:
        return <SampleReports />;
    }
  };

  return (
    <div className="flex h-full bg-background overflow-hidden">
      {/* Sidebar */}
      <div
        className={cn(
          "flex flex-col shrink-0 transition-all duration-300",
          sidebarCollapsed ? "w-[72px]" : "w-[240px]"
        )}
      >
        <div className="p-4 flex items-center gap-2 border-b border-border">
          <div className="p-1 border rounded-sm bg-amber-50 border-amber-200 text-amber-600 shrink-0">
            <Factory className="w-4 h-4" />
          </div>
          <span className="font-semibold text-foreground text-l">知识工厂</span>
        </div>
        <TabNavigation
          activeTab={activeTab}
          onTabChange={setActiveTab}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        />
      </div>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">
        <div className="h-full overflow-y-auto">{renderContent()}</div>
      </main>
    </div>
  );
}
