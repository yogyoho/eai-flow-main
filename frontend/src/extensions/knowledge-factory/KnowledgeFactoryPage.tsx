"use client";

import { Factory } from "lucide-react";
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
    <div className="bg-background flex h-full overflow-hidden">
      {/* Sidebar */}
      <div
        className={cn(
          "flex shrink-0 flex-col transition-all duration-300",
          sidebarCollapsed ? "w-[72px]" : "w-[240px]",
        )}
      >
        <div className="border-border flex items-center gap-2 border-b p-4">
          <div className="shrink-0 rounded-sm border border-amber-200 bg-amber-50 p-1 text-amber-600">
            <Factory className="h-4 w-4" />
          </div>
          <span className="text-foreground text-l font-semibold">知识工厂</span>
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
