"use client";

import Link from "next/link";
import { Pen, FileText, LayoutGrid, FolderOpen } from "lucide-react";

const actions = [
  { label: "个人写作", icon: Pen, href: "/" },
  { label: "从模板创建", icon: FileText, href: "/projects?action=create" },
  { label: "项目看板", icon: LayoutGrid, href: "/projects" },
  { label: "我的文档", icon: FolderOpen, href: "/documents" },
];

export function QuickActions() {
  return (
    <div className="flex items-center gap-2">
      {actions.map((a) => (
        <Link
          key={a.label}
          href={a.href}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <a.icon className="h-4 w-4" />
          <span className="hidden sm:inline">{a.label}</span>
        </Link>
      ))}
    </div>
  );
}
