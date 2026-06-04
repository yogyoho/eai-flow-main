"use client";

import Link from "next/link";
import { LayoutGrid, FolderOpen, FileText, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface QuickLinkItem {
  label: string;
  icon: LucideIcon;
  href: string;
  bg: string;
  text: string;
}

const links: QuickLinkItem[] = [
  { label: "项目看板", icon: LayoutGrid, href: "/projects", bg: "bg-blue-50", text: "text-blue-600" },
  { label: "我的文档", icon: FolderOpen, href: "/documents", bg: "bg-emerald-50", text: "text-emerald-600" },
  { label: "模板中心", icon: FileText, href: "/projects?action=create", bg: "bg-violet-50", text: "text-violet-600" },
  { label: "系统设置", icon: Settings, href: "/settings", bg: "bg-amber-50", text: "text-amber-600" },
];

export function QuickLinks() {
  return (
    <div className="grid grid-cols-2 gap-3">
      {links.map((item) => (
        <Link
          key={item.label}
          href={item.href}
          className="group flex flex-col items-center gap-1.5 rounded-lg border border-border p-3 hover:shadow-md transition-all"
        >
          <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${item.bg} ${item.text} transition-transform group-hover:scale-110`}>
            <item.icon className="h-4.5 w-4.5" />
          </div>
          <span className="text-xs font-medium text-foreground">{item.label}</span>
        </Link>
      ))}
    </div>
  );
}
