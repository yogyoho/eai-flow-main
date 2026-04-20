"use client";

import { LayoutDashboard } from "lucide-react";
import React, { useState } from "react";

import type { TabId } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

import {
  SampleReports,
  TemplateExtraction,
  TemplateEditor,
  LawLibrary,
  RuleEngine,
  VersionControl,
  QualityAssessment,
  WebScraper,
  TabNavigation,
} from "@/extensions/knowledge-factory/index";
import DraftBox from "./DraftBox";

export default function KnowledgeFactoryPage() {
  const [activeTab, setActiveTab] = useState<TabId>("reports");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showDraftBox, setShowDraftBox] = useState(false);

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
        return (
          <div className="relative h-full">
            <WebScraper onOpenDraftBox={() => setShowDraftBox(true)} />
            {showDraftBox && (
              <div className="absolute inset-0 bg-background z-10">
                <DraftBox onClose={() => setShowDraftBox(false)} />
              </div>
            )}
          </div>
        );
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
