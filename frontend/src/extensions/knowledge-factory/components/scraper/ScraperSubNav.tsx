"use client";

import { BarChart3, Database, FileText } from "lucide-react";
import React from "react";

import { cn } from "@/lib/utils";

import { useScraperContext } from "./ScraperContext";

const SUB_TABS = [
  { id: "task-center", label: "任务中心", icon: BarChart3, desc: "查看抓取任务队列与历史" },
  { id: "source-manager", label: "数据源管理", icon: Database, desc: "管理抓取数据来源" },
  { id: "draft-box", label: "草稿箱", icon: FileText, desc: "管理抓取结果草稿" },
] as const;

export default function ScraperSubNav() {
  const { activeSubTab, setActiveSubTab } = useScraperContext();

  return (
    <div className="flex items-center gap-0.5 px-4 py-1 border-b bg-card/50 backdrop-blur-sm shrink-0">
      {SUB_TABS.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeSubTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => setActiveSubTab(tab.id)}
            title={tab.desc}
            className={cn(
              "relative flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-all duration-200 rounded-lg",
              isActive
                ? "text-primary bg-primary/8 shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            )}
          >
            <Icon className={cn("h-4 w-4 transition-colors", isActive ? "text-primary" : "")} />
            <span>{tab.label}</span>
            {isActive && (
              <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-5 h-0.5 bg-primary rounded-full" />
            )}
          </button>
        );
      })}
    </div>
  );
}
