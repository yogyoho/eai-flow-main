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
  BookOpen,
} from "lucide-react";
import React from "react";

import { usePermission } from "@/core/permissions";
import type { TabId } from "@/extensions/knowledge-factory/types";
import { cn } from "@/lib/utils";

interface NavItem {
  id: TabId;
  label: string;
  icon: React.ElementType;
  pageId: string;
}

// EAI-CUSTOM: 每个 tab 映射到子页面权限点（/api/permissions/me 的 pages），供 canPage 过滤
const NAV_ITEMS: NavItem[] = [
  {
    id: "reports",
    label: "样例管理",
    icon: FileText,
    pageId: "kf:page:sample",
  },
  {
    id: "extraction",
    label: "模板抽取",
    icon: Settings,
    pageId: "kf:page:extraction",
  },
  { id: "editor", label: "模板编辑", icon: Edit3, pageId: "kf:page:template" },
  { id: "law", label: "法规标准", icon: Library, pageId: "kf:page:law" },
  {
    id: "rules",
    label: "合规规则",
    icon: ShieldCheck,
    pageId: "kf:page:compliance",
  },
  {
    id: "version",
    label: "版本管理",
    icon: GitBranch,
    pageId: "kf:page:version",
  },
  {
    id: "quality",
    label: "质量评估",
    icon: BarChart3,
    pageId: "kf:page:quality",
  },
  { id: "scraper", label: "网页爬取", icon: Globe, pageId: "kf:page:scrape" },
  {
    id: "dictionaries",
    label: "业务字典",
    icon: BookOpen,
    pageId: "kf:page:dict",
  },
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
  const { canPage, isLoading } = usePermission();
  // EAI-CUSTOM: 权限加载中 fail-open 全显，加载完成后按 canPage(pageId) 过滤不可见 tab
  const visibleItems = isLoading
    ? NAV_ITEMS
    : NAV_ITEMS.filter((n) => canPage(n.pageId));

  return (
    <nav className="bg-card border-border flex h-full flex-col border-r">
      <div className="flex-1 space-y-1 overflow-y-auto p-3">
        {visibleItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onTabChange(item.id)}
            className={cn(
              "group relative flex w-full items-center gap-3 rounded-xl px-3 py-3 transition-all",
              activeTab === item.id
                ? "bg-secondary text-primary font-normal"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {!collapsed && (
              <span className="text-sm font-normal whitespace-nowrap">
                {item.label}
              </span>
            )}
            {activeTab === item.id && (
              <div className="bg-primary absolute left-0 h-6 w-1 rounded-r-full" />
            )}
          </button>
        ))}
      </div>
      {onToggleCollapse && (
        <div className="border-border border-t p-3">
          <button
            onClick={onToggleCollapse}
            className="hover:bg-accent text-muted-foreground flex w-full items-center justify-center rounded-xl p-2 transition-colors"
          >
            {collapsed ? (
              <ChevronRight className="h-5 w-5" />
            ) : (
              <ChevronLeft className="h-5 w-5" />
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
