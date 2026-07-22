/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import { CheckCircle, Circle, Trash2, ListChecks, ArrowUpRight, Activity, Cpu, ShieldAlert, Database } from "lucide-react";
import { Task } from "../types.js";
import { motion, AnimatePresence } from "motion/react";

interface TaskCenterProps {
  tasks: Task[];
  onToggleTask: (id: string) => void;
  onAddTask: (taskData: { title: string; category: Task["category"]; priority: Task["priority"] }) => void;
  onDeleteTask: (id: string) => void;
}

export default function TaskCenter({
  tasks,
  onToggleTask,
  onAddTask,
  onDeleteTask,
}: TaskCenterProps) {
  const [activeTab, setActiveTab] = useState<"pending" | "completed">("pending");
  const [titleInput, setTitleInput] = useState("");
  const [category, setCategory] = useState<Task["category"]>("Compute");
  const [priority, setPriority] = useState<Task["priority"]>("medium");
  const [isAdding, setIsAdding] = useState(false);

  const filteredTasks = tasks.filter(t => t.status === activeTab);
  const pendingCount = tasks.filter(t => t.status === "pending").length;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!titleInput.trim()) return;
    onAddTask({
      title: titleInput,
      category,
      priority,
    });
    setTitleInput("");
    setIsAdding(false);
  };

  const getPriorityColor = (lvl: Task["priority"]) => {
    switch (lvl) {
      case "critical": return "border-red-500 bg-red-500/10 text-red-400 shadow-[0_0_8px_rgba(239,68,68,0.2)]";
      case "high": return "border-amber-500 bg-amber-500/10 text-amber-500";
      case "medium": return "border-cyan-500 bg-cyan-500/10 text-cyan-550";
      default: return "border-slate-350 bg-slate-100 text-slate-600 dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-400";
    }
  };

  const getCategoryIcon = (cat: Task["category"]) => {
    switch (cat) {
      case "Security": return <ShieldAlert className="w-4 h-4 text-purple-500" />;
      case "Database": return <Database className="w-4 h-4 text-emerald-500" />;
      default: return <Cpu className="w-4 h-4 text-cyan-500" />;
    }
  };

  return (
    <div className="themed-card rounded-xl p-4 md:p-6 relative flex flex-col h-full overflow-hidden">
      {/* Corner design flourishes */}
      <div className="absolute top-0 right-0 w-3 h-3 bg-cyan-500/20 clip-corners" />

      {/* Card Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 text-blue-500 rounded-md">
            <ListChecks className="w-4 h-4" />
          </div>
          <h2 className="text-sm font-bold tracking-wider themed-text-primary uppercase font-cyber flex items-center gap-1.5">
            我的待办 <span className="text-xs font-normal text-slate-500">My Task Matrix</span>
          </h2>
        </div>

        {/* Counts indicator */}
        <div className="flex items-center gap-2 font-cyber text-xs">
          <button
            onClick={() => setActiveTab("pending")}
            className={`px-2.5 py-1 rounded transition-all cursor-pointer ${activeTab === "pending" ? "bg-cyan-500/15 border border-cyan-500/30 text-cyan-500 font-bold" : "text-slate-550 hover:text-slate-700 dark:hover:text-slate-300"}`}
          >
            待办 ({pendingCount})
          </button>
          <button
            onClick={() => setActiveTab("completed")}
            className={`px-2.5 py-1 rounded transition-all cursor-pointer ${activeTab === "completed" ? "bg-emerald-500/15 border border-emerald-500/30 text-emerald-500 font-bold" : "text-slate-550 hover:text-slate-700 dark:hover:text-slate-300"}`}
          >
            已完成 ({tasks.length - pendingCount})
          </button>
        </div>
      </div>

      {/* Quick Add Form Trigger */}
      <div className="mb-4">
        {!isAdding ? (
          <button
            onClick={() => setIsAdding(true)}
            className="w-full py-2 px-3 border border-dashed border-[var(--border-color)] hover:border-cyan-500/30 bg-slate-400/5 hover:bg-slate-400/10 text-[var(--text-muted)] hover:text-cyan-550 rounded-lg text-xs font-sans transition-all flex items-center justify-center gap-1 cursor-pointer"
          >
            <span>+ 部署新任务调度协议</span>
          </button>
        ) : (
          <motion.form
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            onSubmit={handleSubmit}
            className="p-3 border border-[var(--border-color-muted)] rounded-lg bg-slate-400/5 text-xs flex flex-col gap-3"
          >
            <div>
              <label className="block text-[var(--text-muted)] font-bold mb-1 font-sans">协议名称 / Task Title</label>
              <input
                type="text"
                required
                value={titleInput}
                onChange={e => setTitleInput(e.target.value)}
                placeholder="例如: 重建数据库索引分析或安全测试..."
                className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] focus:border-cyan-550 rounded px-2 py-1.5 text-[var(--text-main)] outline-none font-sans transition-colors duration-200"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[var(--text-muted)] font-bold mb-1">子系统 / Category</label>
                <select
                  value={category}
                  onChange={e => setCategory(e.target.value as Task["category"])}
                  className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] focus:border-cyan-550 rounded px-2 py-1 text-[var(--text-main)] outline-none cursor-pointer"
                >
                  <option value="Compute">计算子核 (Compute)</option>
                  <option value="Security">安全沙箱 (Security)</option>
                  <option value="Database">数据库群 (Database)</option>
                  <option value="Core">主控核心 (Core)</option>
                </select>
              </div>

              <div>
                <label className="block text-[var(--text-muted)] font-bold mb-1">优先级 / Priority</label>
                <select
                  value={priority}
                  onChange={e => setPriority(e.target.value as Task["priority"])}
                  className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] focus:border-cyan-550 rounded px-2 py-1 text-[var(--text-main)] outline-none cursor-pointer"
                >
                  <option value="low">低 (Low)</option>
                  <option value="medium">中 (Medium)</option>
                  <option value="high">高 (High)</option>
                  <option value="critical">暴发级 (Critical)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 mt-1">
              <button
                type="button"
                onClick={() => setIsAdding(false)}
                className="px-2.5 py-1 text-slate-550 hover:text-[var(--text-main)] cursor-pointer"
              >
                取消
              </button>
              <button
                type="submit"
                className="px-3 py-1 bg-cyan-600 hover:bg-cyan-550 text-white font-bold rounded cursor-pointer border border-cyan-400/20"
              >
                确立分配
              </button>
            </div>
          </motion.form>
        )}
      </div>

      {/* Task Queue List Area */}
      <div className="flex-1 overflow-y-auto max-h-[300px] pr-1.5 flex flex-col gap-2.5">
        <AnimatePresence mode="popLayout">
          {filteredTasks.length === 0 ? (
            activeTab === "pending" ? (
              // Match the clean 'All Completed' state from user screenshot exactly
              <motion.div
                key="empty-state"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center justify-center p-8 text-center flex-1"
              >
                <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mb-3 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
                  <CheckCircle className="w-8 h-8 text-emerald-500 animate-pulse" />
                </div>
                <h3 className="text-sm font-bold text-emerald-600 font-sans tracking-wide">
                  所有任务已完成
                </h3>
                <p className="text-xs text-slate-500 mt-1 font-mono">
                  ALL PROTOCOLS VERIFIED & ALIGNED // 0 QUEUED
                </p>
              </motion.div>
            ) : (
              <p className="text-slate-550 text-xs italic text-center py-8">暂无已完成序列</p>
            )
          ) : (
            filteredTasks.map(task => (
              <motion.div
                key={task.id}
                layout
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="p-3 border border-[var(--border-color-muted)] hover:border-slate-400/40 bg-slate-400/5 hover:bg-slate-400/10 rounded-lg flex items-start justify-between gap-3 group transition-colors shadow-sm"
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  {/* Status Toggle Box */}
                  <button
                    onClick={() => onToggleTask(task.id)}
                    className="mt-0.5 text-slate-500 hover:text-cyan-550 focus:outline-none focus:text-cyan-550 transition-colors cursor-pointer flex-shrink-0"
                  >
                    {task.status === "completed" ? (
                      <CheckCircle className="w-4 h-4 text-emerald-500" />
                    ) : (
                      <Circle className="w-4 h-4 text-slate-400 dark:text-slate-650 group-hover:text-cyan-500" />
                    )}
                  </button>

                  <div className="min-w-0">
                    <p className={`text-xs font-semibold leading-relaxed ${task.status === "completed" ? "text-slate-400 dark:text-slate-500 line-through font-normal" : "text-[var(--text-main)] font-sans"}`}>
                      {task.title}
                    </p>
                    {task.description && (
                      <p className="text-[10px] text-slate-505 font-mono mt-0.5 truncate max-w-[280px]">
                        {task.description}
                      </p>
                    )}
                    
                    {/* Tags list */}
                    <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-cyber bg-slate-400/10 text-slate-550 uppercase">
                        {getCategoryIcon(task.category)}
                        {task.category}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-cyber border capitalize ${getPriorityColor(task.priority)}`}>
                        {task.priority}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Trash Button */}
                <button
                  onClick={() => onDeleteTask(task.id)}
                  className="text-slate-500 hover:text-red-500 p-1 rounded hover:bg-slate-400/10 opacity-0 group-hover:opacity-100 transition-all cursor-pointer flex-shrink-0"
                  title="撤除任务调度"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
