/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import { Terminal, Send, Cpu, Disc, Sparkles } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

interface AIPanelProps {
  onAnalyze: (customQuery?: string) => Promise<string>;
}

export default function AIPanel({ onAnalyze }: AIPanelProps) {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const presetQueries = [
    { label: "核心运行审计", text: "对我当前的进行中项目 and 任务队列做一次全面健康度与节点分布评估" },
    { label: "排期优化指令", text: "基于我现有的紧急情况优先级排程，提出节点重分配与提效建议" },
    { label: "安全壁垒态势", text: "计算安全沙箱与防御机制的潜在脆弱漏洞风险" }
  ];

  const handleQuerySubmit = async (textToSubmit: string) => {
    if (loading) return;
    setLoading(true);
    setResponse("");
    try {
      const result = await onAnalyze(textToSubmit);
      setResponse(result);
    } catch {
      setResponse("COM_ERROR: STARDOCK NEURAL LINK DISCONNECTED. RETRY PROTOCOL HANDSHAKE.");
    } finally {
      setLoading(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    handleQuerySubmit(query);
    setQuery("");
  };

  return (
    <div className="themed-card rounded-xl p-4 md:p-6 relative flex flex-col min-h-[300px]">
      {/* Absolute floating cyber icons */}
      <div className="absolute top-0 right-0 w-3 h-3 bg-cyan-500/10 border-b border-l border-cyan-500/30" />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3 mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-cyan-500/15 border border-cyan-500/20 text-cyan-500 rounded-md shadow-[0_0_10px_rgba(6,182,212,0.15)]">
            <Sparkles className="w-4 h-4 animate-pulse text-cyan-600 dark:text-cyan-300" />
          </div>
          <h2 className="text-sm font-bold tracking-wider themed-text-primary uppercase font-cyber flex items-center gap-1.5">
            AI 决策之脑 <span className="text-xs font-normal text-slate-500">Prometheus Neural Advisor</span>
          </h2>
        </div>
        <span className="text-[10px] font-cyber px-2 py-0.5 rounded border border-cyan-500/20 bg-cyan-500/5 text-cyan-600 dark:text-cyan-400 font-bold tracking-widest text-shadow-glow">
          MODEL: FLASH-3.5
        </span>
      </div>

      {/* Presets Grid */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        {presetQueries.map((preset, i) => (
          <button
            key={i}
            onClick={() => handleQuerySubmit(preset.text)}
            disabled={loading}
            className="p-2 border border-[var(--border-color-muted)] bg-slate-400/5 hover:bg-slate-400/15 hover:border-cyan-500/40 text-[var(--text-muted)] hover:text-cyan-600 rounded text-[11px] leading-tight font-sans transition-all text-left cursor-pointer flex flex-col justify-between align-start h-14"
          >
            <span className="font-bold">{preset.label}</span>
            <span className="text-[9px] text-slate-500 font-mono">⚡ ACTIVATE</span>
          </button>
        ))}
      </div>

      {/* Terminal Dialogue Output */}
      <div className="flex-1 min-h-[160px] max-h-[300px] border border-cyan-500/10 rounded-lg bg-[var(--bg-tertiary)] p-3.5 overflow-y-auto mb-4 font-mono text-[11px] leading-relaxed relative flex flex-col shadow-inner">
        {loading ? (
          <div className="flex flex-col items-center justify-center m-auto gap-2.5 text-cyan-600 dark:text-cyan-400 font-cyber">
            <Disc className="w-6 h-6 animate-spin text-cyan-555" />
            <span className="animate-pulse tracking-widest uppercase">&gt; NEURAL COMPILING IN PROCESS...</span>
          </div>
        ) : response ? (
          <pre className="text-[var(--text-main)] whitespace-pre-wrap font-sans text-xs select-all text-left leading-relaxed">
            <div className="text-[10px] text-cyan-600 dark:text-cyan-400 font-cyber border-b border-cyan-500/15 pb-1.5 mb-2 flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5" />
              <span>STARDOCK SYSTEM HEALTH ADVICE COMPILATION</span>
            </div>
            {response}
          </pre>
        ) : (
          <div className="flex flex-col items-center justify-center m-auto text-center px-4 max-w-sm">
            <Terminal className="w-6 h-6 text-slate-400 dark:text-slate-650 mb-2 animate-pulse" />
            <p className="text-slate-500 font-sans">
              &gt; Prometheus neural model offline. Initialize health queries, risk profiling, scheduling advice.
            </p>
          </div>
        )}
      </div>

      {/* Query Console Form */}
      <form onSubmit={handleFormSubmit} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="问问AI核心，例如 '如何重分配节点，并评估量子列阵项目'..."
          disabled={loading}
          className="flex-1 bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] text-[var(--text-main)] rounded-lg px-3 py-2 text-xs outline-none focus:border-cyan-500/40 text-left font-sans placeholder-slate-500"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-3 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-400/10 disabled:border-transparent border border-cyan-400/20 text-white rounded-lg flex items-center justify-center transition-all cursor-pointer"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>
    </div>
  );
}
