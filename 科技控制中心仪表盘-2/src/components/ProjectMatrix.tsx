/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import { FolderGit, Layers, Server, Activity, ArrowRight, ShieldAlert, BadgeInfo } from "lucide-react";
import { Project } from "../types.js";
import { motion, AnimatePresence } from "motion/react";

interface ProjectMatrixProps {
  projects: Project[];
  onAddProject: (projData: { name: string; description: string; systemLoad: number; coreNodes: number }) => void;
  onSelectProject?: (name: string) => void;
}

export default function ProjectMatrix({
  projects,
  onAddProject,
  onSelectProject,
}: ProjectMatrixProps) {
  const [showAddQuick, setShowAddQuick] = useState(false);
  const [quickName, setQuickName] = useState("");
  const [quickLoad, setQuickLoad] = useState(35);
  const [quickNodes, setQuickNodes] = useState(4);

  const handleQuickSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickName.trim()) return;
    onAddProject({
      name: quickName,
      description: "Auto-calibrated resource pool node matrix.",
      systemLoad: quickLoad,
      coreNodes: quickNodes,
    });
    setQuickName("");
    setShowAddQuick(false);
  };

  return (
    <div className="themed-card rounded-xl p-4 md:p-6 relative flex flex-col h-full overflow-hidden">
      {/* Visual cybernetic scanner style decoration lines */}
      <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent" />
      <div className="absolute bottom-0 right-0 w-3 h-3 bg-purple-500/20 clip-corners" />

      {/* Title block */}
      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-purple-500/10 border border-purple-500/20 text-purple-500 rounded-md">
            <Layers className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-wider themed-text-primary uppercase font-cyber flex items-center gap-1.5">
            我的项目 <span className="text-xs font-normal text-slate-500">Project Nodes</span>
          </h2>
        </div>

        <button
          onClick={() => setShowAddQuick(!showAddQuick)}
          className="text-xs text-purple-500 hover:text-purple-400 font-cyber flex items-center gap-1 mt-0.5 cursor-pointer"
        >
          {showAddQuick ? "✖ 关闭" : "⚡ 快速分配节点"}
        </button>
      </div>

      {/* Quick Add Project Box */}
      <AnimatePresence>
        {showAddQuick && (
          <motion.form
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            onSubmit={handleQuickSubmit}
            className="mb-4 p-3 border border-purple-555/20 bg-purple-500/5 rounded-lg text-xs overflow-hidden flex flex-col gap-2.5"
          >
            <div>
              <label className="block text-[var(--text-muted)] font-bold mb-1 font-sans">节点项目名称 / Project Node Name</label>
              <input
                type="text"
                required
                value={quickName}
                onChange={e => setQuickName(e.target.value)}
                placeholder="例如: 智能舆情遥测解译网..."
                className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] focus:border-purple-555/50 rounded px-2 py-1 text-[var(--text-main)] outline-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[var(--text-muted)] font-bold mb-1 font-sans">系统载荷 (Load %)</label>
                <input
                  type="number"
                  min="5"
                  max="100"
                  value={quickLoad}
                  onChange={e => setQuickLoad(parseInt(e.target.value))}
                  className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded px-2 py-1 text-[var(--text-main)] outline-none"
                />
              </div>
              <div>
                <label className="block text-[var(--text-muted)] font-bold mb-1 font-sans">核心节点数 (Core Nodes)</label>
                <input
                  type="number"
                  min="1"
                  max="64"
                  value={quickNodes}
                  onChange={e => setQuickNodes(parseInt(e.target.value))}
                  className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] rounded px-2 py-1 text-[var(--text-main)] outline-none"
                />
              </div>
            </div>
            <button
              type="submit"
              className="w-full py-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:opacity-90 border border-purple-400/20 text-white font-bold rounded cursor-pointer mt-1"
            >
              初始化系统共鸣
            </button>
          </motion.form>
        )}
      </AnimatePresence>

      {/* Main projects container */}
      <div className="flex-1 overflow-y-auto max-h-[350px] pr-1.5 flex flex-col gap-4">
        {projects.length === 0 ? (
          // Match '暂无项目' state from user screenshot exactly
          <div className="flex flex-col items-center justify-center py-14 text-center animate-fade-in">
            <div className="w-16 h-16 rounded-full bg-slate-400/10 border border-slate-400/20 flex items-center justify-center mb-3 text-slate-500">
              <FolderGit className="w-8 h-8" />
            </div>
            <h3 className="text-sm font-semibold text-slate-500">暂无项目</h3>
            <p className="text-[10px] text-slate-500 font-mono mt-1">NO ACTIVE WORKSPACE PROJECTS LOADED</p>
            <button
              onClick={() => setShowAddQuick(true)}
              className="mt-4 px-3 py-1.5 bg-purple-500/15 text-purple-600 hover:text-purple-500 rounded border border-purple-500/20 font-sans text-xs hover:border-purple-500/40 transition-all cursor-pointer font-bold"
            >
              初始智能核准项目
            </button>
          </div>
        ) : (
          projects.map(proj => (
            <div
              key={proj.id}
              onClick={() => onSelectProject && onSelectProject(proj.name)}
              className="p-4 border border-[var(--border-color-muted)] hover:border-purple-500/30 bg-slate-400/5 hover:bg-slate-400/10 rounded-lg group transition-all duration-200 cursor-pointer"
            >
              <div className="flex items-start justify-between gap-3 mb-2.5">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <h3 className="text-sm font-bold text-[var(--text-main)] tracking-wide truncate group-hover:text-purple-500 dark:group-hover:text-purple-300 font-sans transition-colors">
                      {proj.name}
                    </h3>
                    <span className="text-[9px] text-purple-500 group-hover:translate-x-0.5 opacity-0 group-hover:opacity-100 transition-all font-sans font-semibold">
                      进入报告编写 →
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 font-sans mt-0.5 max-w-[420px] leading-normal line-clamp-2">
                    {proj.description}
                  </p>
                </div>

                {/* Progress Circle Visual */}
                <div className="relative w-12 h-12 flex-shrink-0 flex items-center justify-center">
                  <svg className="w-full h-full transform -rotate-90">
                    <circle
                      cx="24"
                      cy="24"
                      r="19"
                      className="text-slate-100 dark:text-slate-800"
                      strokeWidth="3.5"
                      stroke="currentColor"
                      fill="transparent"
                    />
                    <motion.circle
                      cx="24"
                      cy="24"
                      r="19"
                      className="text-purple-500 glow-purple"
                      strokeWidth="3.5"
                      strokeDasharray={`${2 * Math.PI * 19}`}
                      strokeDashoffset={`${2 * Math.PI * 19 * (1 - proj.progress / 100)}`}
                      strokeLinecap="round"
                      stroke="currentColor"
                      fill="transparent"
                      initial={{ strokeDashoffset: 120 }}
                      animate={{ strokeDashoffset: 119.38 * (1 - proj.progress / 100) }}
                      transition={{ duration: 1.2, ease: "easeOut" }}
                    />
                  </svg>
                  <span className="absolute text-[10px] font-bold text-[var(--text-main)] font-cyber">{proj.progress}%</span>
                </div>
              </div>

              {/* Loader glowing slider */}
              <div className="w-full h-1 bg-slate-100 dark:bg-slate-850 rounded-full overflow-hidden mb-3.5 relative">
                <div
                  className="h-full bg-gradient-to-r from-purple-500 to-indigo-500 glow-purple transition-all duration-1000"
                  style={{ width: `${proj.progress}%` }}
                />
              </div>

              {/* Status and telemetry meters */}
              <div className="flex items-center justify-between text-[11px] font-cyber text-slate-500 border-t border-[var(--border-color-muted)] pt-2.5">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1.5 text-slate-500">
                    <Server className="w-3 h-3 text-slate-400" />
                    节点: <span className="text-[var(--text-main)] font-bold">{proj.coreNodes} NODES</span>
                  </span>
                  
                  <span className="flex items-center gap-1.5 text-slate-500">
                    <Activity className="w-3 h-3 text-slate-400" />
                    负载: <span className="text-purple-400 font-bold">{proj.systemLoad}%</span>
                  </span>
                </div>

                <span className={`px-2 py-0.5 rounded text-[9px] uppercase font-bold border ${
                  proj.status === "active" ? "bg-cyan-500/10 border-cyan-500/20 text-cyan-400" :
                  proj.status === "review" ? "bg-amber-500/10 border-amber-500/20 text-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.1)]" :
                  proj.status === "completed" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" :
                  "bg-slate-800 border-slate-700 text-slate-500"
                }`}>
                  {proj.status === "active" ? "进行中 (Active)" :
                   proj.status === "review" ? "待审核 (Review)" :
                   proj.status === "completed" ? "完成 (Completed)" : "休眠 (Paused)"}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
