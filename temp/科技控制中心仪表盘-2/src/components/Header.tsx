/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from "react";
import { Terminal, Shield, Plus, BrainCircuit, Waves, Sun, Moon } from "lucide-react";
import { motion } from "motion/react";

interface HeaderProps {
  onOpenNewProject: () => void;
  onOpenKnowledgeTrigger: () => void;
  pendingTasksCount: number;
  totalTasksCount: number;
  isDarkMode: boolean;
  onToggleTheme: () => void;
}

export default function Header({
  onOpenNewProject,
  onOpenKnowledgeTrigger,
  pendingTasksCount,
  totalTasksCount,
  isDarkMode,
  onToggleTheme,
}: HeaderProps) {
  const [time, setTime] = useState("");
  const [millis, setMillis] = useState("");
  const [systemLoad, setSystemLoad] = useState(45.2);

  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      // Format local time: YYYY年MM月DD日 HH:mm:ss
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, "0");
      const date = String(now.getDate()).padStart(2, "0");
      const hours = String(now.getHours()).padStart(2, "0");
      const minutes = String(now.getMinutes()).padStart(2, "0");
      const seconds = String(now.getSeconds()).padStart(2, "0");
      
      setTime(`${year}年${month}月${date}日 ${hours}:${minutes}:${seconds}`);
      
      const ms = String(now.getMilliseconds()).padStart(3, "0");
      setMillis(ms);
    }, 100);

    const loadTimer = setInterval(() => {
      // Simulate microscopic load fluctuations
      setSystemLoad(prev => {
        const delta = (Math.random() - 0.5) * 1.5;
        const next = prev + delta;
        return parseFloat(Math.min(Math.max(next, 38.0), 52.0).toFixed(2));
      });
    }, 2000);

    return () => {
      clearInterval(timer);
      clearInterval(loadTimer);
    };
  }, []);

  // Determine greeting based on local hour
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 6) return "凌晨好";
    if (hour < 12) return "上午好";
    if (hour < 14) return "中午好";
    if (hour < 18) return "下午好";
    return "晚上好";
  };

  return (
    <header className={`relative w-full border-b transition-colors duration-300 p-4 md:px-8 md:py-5 backdrop-blur-md z-10 scanlines ${
      isDarkMode 
        ? "border-cyan-500/15 bg-slate-950/80" 
        : "border-slate-200 bg-white/90 shadow-[0_1px_10px_rgba(0,0,0,0.03)]"
    }`}>
      {/* Background glow node */}
      {isDarkMode && (
        <div className="absolute top-0 left-1/4 w-1/3 h-24 bg-cyan-500/10 rounded-full blur-[100px] pointer-events-none" />
      )}

      <div className="flex flex-col md:flex-row md:items-center md:justify-between justify-start gap-4">
        {/* Identity & Status Greeting */}
        <div className="flex items-start gap-3">
          <div className={`p-3 border rounded-lg transition-all duration-300 flex items-center justify-center ${
            isDarkMode 
              ? "bg-cyan-950/40 border-cyan-500/30 text-cyan-400 glow-cyan" 
              : "bg-cyan-50 border-cyan-200 text-cyan-600 shadow-[0_0_12px_rgba(6,182,212,0.15)]"
          }`}>
            <Shield className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className={`text-xl md:text-2xl font-bold tracking-tight font-sans transition-colors ${
                isDarkMode ? "text-white" : "text-slate-900"
              }`}>
                {getGreeting()}, <span className={`text-transparent bg-clip-text bg-gradient-to-r font-extrabold ${
                  isDarkMode ? "from-cyan-400 to-purple-400" : "from-cyan-600 to-purple-600"
                }`}>Administrator</span>
              </h1>
              <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] uppercase font-bold font-cyber border transition-all ${
                isDarkMode 
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.15)]" 
                  : "border-emerald-200 bg-emerald-50 text-emerald-600"
              }`}>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                Secure Mode
              </span>
            </div>
            
            <p className={`text-xs md:text-sm mt-1 font-mono flex items-center gap-2 transition-colors ${
              isDarkMode ? "text-slate-400" : "text-slate-600"
            }`}>
              <span className={isDarkMode ? "text-cyan-400" : "text-cyan-600"}>⚡ 系统就绪</span>
              <span className="text-slate-300">|</span>
              <span>{pendingTasksCount === 0 ? "所有任务已完成" : `待办任务: ${pendingTasksCount} / ${totalTasksCount}`}</span>
              <span className="text-slate-300">|</span>
              <span className="hidden sm:inline">{time}</span>
              <span className={`font-bold hidden sm:inline font-mono ${isDarkMode ? "text-cyan-500" : "text-cyan-600"}`}>.{millis} MS</span>
            </p>
          </div>
        </div>

        {/* Dynamic Telemetry readout */}
        <div className={`hidden lg:flex items-center gap-6 border-l pl-6 text-xs font-cyber transition-colors ${
          isDarkMode ? "border-slate-800 text-slate-400" : "border-slate-200 text-slate-650"
        }`}>
          <div className="flex items-center gap-2">
            <Waves className={`w-4 h-4 animate-pulse ${isDarkMode ? "text-cyan-400" : "text-cyan-600"}`} />
            <div>
              <div className="text-slate-550 uppercase text-[9px] tracking-wider">SYS CORE EFFICIENCY</div>
              <div className={`font-bold text-sm flex items-end gap-1 ${isDarkMode ? "text-white text-shadow-glow" : "text-slate-900"}`}>
                99.87<span className={`${isDarkMode ? "text-cyan-400" : "text-cyan-600"} text-[10px]`}>%</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <BrainCircuit className={`w-4 h-4 ${isDarkMode ? "text-purple-400" : "text-purple-600"}`} />
            <div>
              <div className="text-slate-550 uppercase text-[9px] tracking-wider">HEURISTIC ADAPTIVITY</div>
              <div className={`font-bold text-sm flex items-end gap-1 ${isDarkMode ? "text-white" : "text-slate-900"}`}>
                {systemLoad}<span className={`${isDarkMode ? "text-purple-400" : "text-purple-600"} text-[10px]`}>%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-3">
          {/* Theme switcher */}
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={onToggleTheme}
            className={`p-2.5 rounded-lg border transition-all duration-300 cursor-pointer flex items-center justify-center ${
              isDarkMode 
                ? "bg-slate-900/80 border-slate-800 text-amber-400 hover:text-amber-300 hover:bg-slate-800" 
                : "bg-slate-100 border-slate-200 text-slate-700 hover:text-slate-900 hover:bg-slate-200 shadow-sm"
            }`}
            title={isDarkMode ? "切换到日光模式" : "切换到极客暗黑模式"}
          >
            {isDarkMode ? <Sun className="w-4.5 h-4.5" /> : <Moon className="w-4.5 h-4.5" />}
          </motion.button>

          {/* Create Project Button */}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onOpenNewProject}
            className="flex items-center gap-1.5 px-4 py-2.5 bg-gradient-to-r from-blue-600 to-cyan-500 text-white rounded-lg text-sm font-semibold shadow-lg hover:shadow-cyan-500/20 active:opacity-90 outline-none border border-cyan-400/20 cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>新建项目</span>
          </motion.button>

          {/* Knowledge Process Action Button */}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onOpenKnowledgeTrigger}
            className={`flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all shadow-md cursor-pointer font-sans border ${
              isDarkMode 
                ? "bg-slate-900/80 hover:bg-slate-800 text-cyan-300 hover:text-cyan-200 border-slate-700 hover:border-cyan-500/40" 
                : "bg-slate-100 hover:bg-slate-200 text-cyan-700 hover:text-cyan-800 border-slate-250 hover:border-cyan-500/40"
            }`}
          >
            <BrainCircuit className={`w-4 h-4 animate-spin-slow ${isDarkMode ? "text-purple-400" : "text-purple-600"}`} />
            <span>知识加工</span>
          </motion.button>
        </div>
      </div>
    </header>
  );
}
