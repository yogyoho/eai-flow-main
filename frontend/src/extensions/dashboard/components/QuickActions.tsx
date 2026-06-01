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
    <div className="flex flex-wrap gap-3">
      {actions.map((a) => (
        <Link
          key={a.label}
          href={a.href}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border hover:bg-accent/50 transition-colors text-sm"
        >
          <a.icon className="h-4 w-4" />
          {a.label}
        </Link>
      ))}
    </div>
  );
}
