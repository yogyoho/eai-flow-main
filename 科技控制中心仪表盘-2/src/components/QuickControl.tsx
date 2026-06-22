/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import { Grid3X3, Folder, FileText, Settings, Compass, Command } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

interface QuickControlProps {
  onTriggerAction: (actionName: string) => void;
}

export default function QuickControl({ onTriggerAction }: QuickControlProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [activeConsole, setActiveConsole] = useState<string | null>(null);

  const entries = [
    {
      title: "项目看板",
      subtitle: "Project Kanban",
      color: "text-blue-500 border-blue-500/20 bg-blue-500/5 hover:border-blue-500/40",
      glowColor: "shadow-blue-500/10",
      icon: <Grid3X3 className="w-5 h-5 text-blue-500 group-hover:scale-110 transition-transform" />,
      info: "Open complete multiregion Kanban board."
    },
    {
      title: "我的文档",
      subtitle: "My Documents",
      color: "text-emerald-500 border-emerald-500/20 bg-emerald-500/5 hover:border-emerald-500/40",
      glowColor: "shadow-emerald-500/10",
      icon: <Folder className="w-5 h-5 text-emerald-500 group-hover:scale-110 transition-transform" />,
      info: "Enter quantum drive and file nodes."
    },
    {
      title: "模板中心",
      subtitle: "Template Center",
      color: "text-purple-500 border-purple-500/20 bg-purple-500/5 hover:border-purple-500/40",
      glowColor: "shadow-purple-500/10",
      icon: <FileText className="w-5 h-5 text-purple-500 group-hover:scale-110 transition-transform" />,
      info: "Deploy vetted boilerplate system configurations."
    },
    {
      title: "系统设置",
      subtitle: "System Settings",
      color: "text-amber-500 border-amber-500/20 bg-amber-500/5 hover:border-amber-500/40",
      glowColor: "shadow-amber-500/10",
      icon: <Settings className="w-5 h-5 text-amber-500 group-hover:rotate-45 transition-transform" />,
      info: "Fine-tune system variables and sandbox parameters."
    },
  ];

  const handleEntryClick = (title: string, info: string) => {
    onTriggerAction(title);
    setActiveConsole(info);
    setTimeout(() => {
      setActiveConsole(null);
    }, 4000);
  };

  return (
    <div className="themed-card rounded-xl p-4 md:p-5 relative flex flex-col transition-colors">
      {/* Target style corners */}
      <div className="absolute top-0 right-0 w-2 h-2 bg-[var(--border-color)]" />
      <div className="absolute bottom-0 left-0 w-2 h-2 bg-[var(--border-color)]" />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1 cursor-pointer bg-emerald-500/10 border border-emerald-500/20 rounded text-emerald-500 animate-pulse">
            <Compass className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-wider themed-text-primary uppercase font-cyber flex items-center gap-1.5">
            快捷入口 <span className="text-xs font-normal text-slate-500">Quick Portal</span>
          </h2>
        </div>
        <span className="text-[10px] font-cyber text-emerald-550 uppercase tracking-widest animate-pulse font-bold">
          Online
        </span>
      </div>

      {/* Main Grids */}
      <div className="grid grid-cols-2 gap-3">
        {entries.map((entry, index) => (
          <motion.div
            key={index}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onMouseEnter={() => setHoveredIndex(index)}
            onMouseLeave={() => setHoveredIndex(null)}
            onClick={() => handleEntryClick(entry.title, entry.info)}
            className={`border rounded-lg p-3 cursor-pointer group flex flex-col items-center justify-center text-center transition-all ${entry.color} hover:border-cyan-554/30 ${hoveredIndex === index ? entry.glowColor : ""}`}
          >
            <div className="p-2 mb-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-color)] group-hover:border-cyan-500/20 group-hover:shadow-[0_0_10px_rgba(6,182,212,0.1)] transition-all">
              {entry.icon}
            </div>
            
            <h3 className="text-xs font-bold text-[var(--text-main)] group-hover:text-cyan-600 dark:group-hover:text-cyan-400 transition-colors font-sans">
              {entry.title}
            </h3>
            <span className="text-[9px] text-slate-500 font-cyber uppercase tracking-wider mt-0.5">
              {entry.subtitle}
            </span>
          </motion.div>
        ))}
      </div>

      {/* Immersive Terminal Overlay readout */}
      <div className="mt-3.5 h-[34px] border border-cyan-500/10 rounded-lg bg-[var(--bg-tertiary)] py-1.5 px-3 flex items-center gap-2 overflow-hidden shadow-inner">
        <Command className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400 animate-pulse flex-shrink-0" />
        <p className="text-[10px] font-cyber text-cyan-600 dark:text-cyan-400 truncate">
          <AnimatePresence mode="wait">
            {activeConsole ? (
              <motion.span
                key="console-msg"
                initial={{ opacity: 0, x: -5 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className="text-shadow-glow"
              >
                &gt; EXEC: {activeConsole}
              </motion.span>
            ) : hoveredIndex !== null ? (
              <motion.span
                key={`hover-${hoveredIndex}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                &gt; CAPABILITY: {entries[hoveredIndex].info}
              </motion.span>
            ) : (
              <span className="text-slate-500">&gt; TERMINAL READY // WAITING FOR SELECTION</span>
            )}
          </AnimatePresence>
        </p>
      </div>
    </div>
  );
}
