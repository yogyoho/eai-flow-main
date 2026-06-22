"use client";

import { Grid3X3, Folder, FileText, Settings, Compass, Command } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const entries = [
  { title: "项目看板", subtitle: "Project Kanban", href: "/projects", icon: <Grid3X3 className="w-5 h-5 text-blue-500 group-hover:scale-110 transition-transform" />, color: "text-blue-500 border-blue-500/20 bg-blue-500/5 hover:border-blue-500/40", glowColor: "shadow-blue-500/10", info: "Open complete multiregion Kanban board." },
  { title: "我的文档", subtitle: "My Documents", href: "/docmgr", icon: <Folder className="w-5 h-5 text-emerald-500 group-hover:scale-110 transition-transform" />, color: "text-emerald-500 border-emerald-500/20 bg-emerald-500/5 hover:border-emerald-500/40", glowColor: "shadow-emerald-500/10", info: "Enter quantum drive and file nodes." },
  { title: "模板中心", subtitle: "Template Center", href: "/projects?action=create", icon: <FileText className="w-5 h-5 text-purple-500 group-hover:scale-110 transition-transform" />, color: "text-purple-500 border-purple-500/20 bg-purple-500/5 hover:border-purple-500/40", glowColor: "shadow-purple-500/10", info: "Deploy vetted boilerplate system configurations." },
  { title: "系统设置", subtitle: "System Settings", href: "/settings", icon: <Settings className="w-5 h-5 text-amber-500 group-hover:rotate-45 transition-transform" />, color: "text-amber-500 border-amber-500/20 bg-amber-500/5 hover:border-amber-500/40", glowColor: "shadow-amber-500/10", info: "Fine-tune system variables and sandbox parameters." },
];

export function QuickPanel() {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [activeConsole, setActiveConsole] = useState<string | null>(null);

  return (
    <div className="db-card rounded-xl p-4 md:p-5 relative flex flex-col">
      <div className="absolute top-0 right-0 w-2 h-2 bg-[var(--db-border-color)]" />
      <div className="absolute bottom-0 left-0 w-2 h-2 bg-[var(--db-border-color)]" />

      <div className="flex items-center justify-between border-b border-[var(--db-border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1 bg-emerald-500/10 border border-emerald-500/20 rounded text-emerald-500 animate-pulse">
            <Compass className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-wider db-text-primary uppercase font-cyber">
            快捷入口 <span className="text-xs font-normal text-slate-500">Quick Portal</span>
          </h2>
        </div>
        <span className="text-[10px] font-cyber text-emerald-600 uppercase tracking-widest animate-pulse font-bold">Online</span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {entries.map((entry, i) => (
          <Link key={i} href={entry.href}
            onMouseEnter={() => setHoveredIndex(i)} onMouseLeave={() => setHoveredIndex(null)}
            onClick={() => { setActiveConsole(entry.info); setTimeout(() => setActiveConsole(null), 4000); }}
            className={`border rounded-lg p-3 cursor-pointer group flex flex-col items-center justify-center text-center transition-all no-underline ${entry.color} ${hoveredIndex === i ? entry.glowColor : ""}`}>
            <div className="p-2 mb-2 rounded-lg bg-[var(--db-bg-tertiary)] border border-[var(--db-border-color)] group-hover:border-blue-500/20 group-hover:shadow-[0_0_10px_rgba(6,182,212,0.1)] transition-all">
              {entry.icon}
            </div>
            <h3 className="text-xs font-bold db-text-primary group-hover:text-blue-600 transition-colors">{entry.title}</h3>
            <span className="text-[9px] text-slate-500 font-cyber uppercase tracking-wider mt-0.5">{entry.subtitle}</span>
          </Link>
        ))}
      </div>

      <div className="mt-3.5 h-[34px] border border-blue-500/10 rounded-lg bg-[var(--db-bg-tertiary)] py-1.5 px-3 flex items-center gap-2 overflow-hidden shadow-inner">
        <Command className="w-3.5 h-3.5 text-blue-600 animate-pulse flex-shrink-0" />
        <p className="text-[10px] font-cyber text-blue-600 truncate">
          {activeConsole ? (
            <span className="text-shadow-glow">&gt; EXEC: {activeConsole}</span>
          ) : hoveredIndex !== null ? (
            <span>&gt; CAPABILITY: {entries[hoveredIndex].info}</span>
          ) : (
            <span className="text-slate-500">&gt; TERMINAL READY // WAITING FOR SELECTION</span>
          )}
        </p>
      </div>
    </div>
  );
}
