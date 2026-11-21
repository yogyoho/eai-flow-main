"use client";

import {
  Grid3X3,
  Folder,
  FileText,
  Settings,
  Compass,
  Command,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const entries = [
  {
    title: "项目看板",
    subtitle: "Project Kanban",
    href: "/projects",
    icon: (
      <Grid3X3 className="h-5 w-5 text-blue-500 transition-transform group-hover:scale-110" />
    ),
    color:
      "text-blue-500 border-blue-500/20 bg-blue-500/5 hover:border-blue-500/40",
    glowColor: "shadow-blue-500/10",
    info: "Open complete multiregion Kanban board.",
  },
  {
    title: "我的文档",
    subtitle: "My Documents",
    href: "/docmgr",
    icon: (
      <Folder className="h-5 w-5 text-emerald-500 transition-transform group-hover:scale-110" />
    ),
    color:
      "text-emerald-500 border-emerald-500/20 bg-emerald-500/5 hover:border-emerald-500/40",
    glowColor: "shadow-emerald-500/10",
    info: "Enter quantum drive and file nodes.",
  },
  {
    title: "模板中心",
    subtitle: "Template Center",
    href: "/projects?action=create",
    icon: (
      <FileText className="h-5 w-5 text-purple-500 transition-transform group-hover:scale-110" />
    ),
    color:
      "text-purple-500 border-purple-500/20 bg-purple-500/5 hover:border-purple-500/40",
    glowColor: "shadow-purple-500/10",
    info: "Deploy vetted boilerplate system configurations.",
  },
  {
    title: "系统设置",
    subtitle: "System Settings",
    href: "/settings",
    icon: (
      <Settings className="h-5 w-5 text-amber-500 transition-transform group-hover:rotate-45" />
    ),
    color:
      "text-amber-500 border-amber-500/20 bg-amber-500/5 hover:border-amber-500/40",
    glowColor: "shadow-amber-500/10",
    info: "Fine-tune system variables and sandbox parameters.",
  },
];

export function QuickPanel() {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [activeConsole, setActiveConsole] = useState<string | null>(null);

  return (
    <div className="db-card relative flex flex-col rounded-xl p-4 md:p-5">
      <div className="absolute top-0 right-0 h-2 w-2 bg-[var(--db-border-color)]" />
      <div className="absolute bottom-0 left-0 h-2 w-2 bg-[var(--db-border-color)]" />

      <div className="mb-4 flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3">
        <div className="flex items-center gap-2">
          <div className="animate-pulse rounded border border-emerald-500/20 bg-emerald-500/10 p-1 text-emerald-500">
            <Compass className="h-4 w-4" />
          </div>
          <h2 className="db-text-primary font-cyber text-sm font-bold tracking-wider uppercase">
            快捷入口{" "}
            <span className="text-xs font-normal text-slate-500">
              Quick Portal
            </span>
          </h2>
        </div>
        <span className="font-cyber animate-pulse text-[10px] font-bold tracking-widest text-emerald-600 uppercase">
          Online
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {entries.map((entry, i) => (
          <Link
            key={i}
            href={entry.href}
            onMouseEnter={() => setHoveredIndex(i)}
            onMouseLeave={() => setHoveredIndex(null)}
            onClick={() => {
              setActiveConsole(entry.info);
              setTimeout(() => setActiveConsole(null), 4000);
            }}
            className={`group flex cursor-pointer flex-col items-center justify-center rounded-lg border p-3 text-center no-underline transition-all ${entry.color} ${hoveredIndex === i ? entry.glowColor : ""}`}
          >
            <div className="mb-2 rounded-lg border border-[var(--db-border-color)] bg-[var(--db-bg-tertiary)] p-2 transition-all group-hover:border-blue-500/20 group-hover:shadow-[0_0_10px_rgba(6,182,212,0.1)]">
              {entry.icon}
            </div>
            <h3 className="db-text-primary text-xs font-bold transition-colors group-hover:text-blue-600">
              {entry.title}
            </h3>
            <span className="font-cyber mt-0.5 text-[9px] tracking-wider text-slate-500 uppercase">
              {entry.subtitle}
            </span>
          </Link>
        ))}
      </div>

      <div className="mt-3.5 flex h-[34px] items-center gap-2 overflow-hidden rounded-lg border border-blue-500/10 bg-[var(--db-bg-tertiary)] px-3 py-1.5 shadow-inner">
        <Command className="h-3.5 w-3.5 flex-shrink-0 animate-pulse text-blue-600" />
        <p className="font-cyber truncate text-[10px] text-blue-600">
          {activeConsole ? (
            <span className="text-shadow-glow">&gt; EXEC: {activeConsole}</span>
          ) : hoveredIndex !== null ? (
            <span>&gt; CAPABILITY: {entries[hoveredIndex]!.info}</span>
          ) : (
            <span className="text-slate-500">
              &gt; TERMINAL READY // WAITING FOR SELECTION
            </span>
          )}
        </p>
      </div>
    </div>
  );
}
