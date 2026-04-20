"use client";

import {
  FileText,
  Settings,
  Edit3,
  Library,
  ShieldCheck,
  GitBranch,
  BarChart3,
  Globe,
} from "lucide-react";
import React from "react";

import type { TabId } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface NavItem {
  id: TabId;
  label: string;
  icon: React.ElementType;
}

const NAV_ITEMS: NavItem[] = [
  { id: "reports", label: "样例管理", icon: FileText },
  { id: "extraction", label: "模板抽取", icon: Settings },
  { id: "editor", label: "模板编辑", icon: Edit3 },
  { id: "law", label: "法规标准", icon: Library },
  { id: "rules", label: "合规规则", icon: ShieldCheck },
  { id: "version", label: "版本管理", icon: GitBranch },
  { id: "quality", label: "质量评估", icon: BarChart3 },
  { id: "scraper", label: "网页爬取", icon: Globe },
];

interface TabNavigationProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function TabNavigation({
  activeTab,
  onTabChange,
  collapsed = false,
  onToggleCollapse,
}: TabNavigationProps) {
  return (
    <nav className="flex flex-col h-full bg-card border-r border-border">
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => onTabChange(item.id)}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-3 rounded-xl transition-all group relative",
              activeTab === item.id
                ? "bg-secondary text-primary font-medium"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <item.icon className="w-5 h-5 shrink-0" />
            {!collapsed && (
              <span className="text-sm font-medium whitespace-nowrap">
                {item.label}
              </span>
            )}
            {activeTab === item.id && (
              <div className="absolute left-0 w-1 h-6 bg-primary rounded-r-full" />
            )}
          </button>
        ))}
      </div>
      {onToggleCollapse && (
        <div className="p-3 border-t border-border">
          <button
            onClick={onToggleCollapse}
            className="w-full flex items-center justify-center p-2 rounded-xl hover:bg-accent text-muted-foreground transition-colors"
          >
            {collapsed ? (
              <ChevronRight className="w-5 h-5" />
            ) : (
              <ChevronLeft className="w-5 h-5" />
            )}
          </button>
        </div>
      )}
    </nav>
  );
}

function ChevronLeft({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

function ChevronRight({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}
