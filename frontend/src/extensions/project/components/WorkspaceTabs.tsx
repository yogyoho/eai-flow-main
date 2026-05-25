"use client";

import Link from "next/link";

import { cn } from "@/lib/utils";

import type { TabConfig } from "../tabRegistry";

export type WorkspaceTab = string;

interface WorkspaceTabsProps {
  projectId: string;
  currentTab: WorkspaceTab;
  tabs: TabConfig[];
}

const ICON_MAP: Record<string, string> = {
  Target: "🎯",
  BarChart3: "📊",
  Kanban: "📋",
  FileText: "📝",
  Users: "👥",
  CheckCircle: "✅",
  Bot: "🤖",
};

export function WorkspaceTabs({ projectId, currentTab, tabs }: WorkspaceTabsProps) {
  return (
    <nav className="flex items-center gap-6 text-sm font-medium text-muted-foreground h-full">
      {tabs.map((tab) => {
        const href = `/projects/${projectId}?tab=${tab.id}`;
        const isActive = currentTab === tab.id;
        return (
          <Link
            key={tab.id}
            href={href}
            className={cn(
              "flex items-center h-full transition-colors py-5 border-b-2",
              isActive
                ? "text-primary border-primary"
                : "border-transparent hover:text-foreground",
            )}
          >
            {ICON_MAP[tab.icon] ?? ""} {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
