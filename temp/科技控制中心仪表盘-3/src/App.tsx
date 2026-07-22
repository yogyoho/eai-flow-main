/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from "react";
import { Terminal, Shield, Sparkles, Sliders, X, Check, Database } from "lucide-react";
import { Task, Project, NotificationLog, CalendarEvent, SystemMetrics, DynamicTelemetry } from "./types.js";
import Header from "./components/Header.tsx";
import TaskCenter from "./components/TaskCenter.tsx";
import ProjectMatrix from "./components/ProjectMatrix.tsx";
import QuickControl from "./components/QuickControl.tsx";
import LogConsole from "./components/LogConsole.tsx";
import MetricsTelemetry from "./components/MetricsTelemetry.tsx";
import SpaceCalendar from "./components/SpaceCalendar.tsx";
import AIPanel from "./components/AIPanel.tsx";
import ProjectDetailPage from "./components/ProjectDetailPage.tsx";
import LandingPage from "./components/LandingPage.tsx";
import ProjectManagement from "./components/ProjectManagement.tsx";
import { motion, AnimatePresence } from "motion/react";

export default function App() {
  const [activePage, setActivePage] = useState<"landing" | "dashboard" | "project-detail">("landing");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [notifications, setNotifications] = useState<NotificationLog[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [metrics, setMetrics] = useState<SystemMetrics>({
    activeProjects: 0,
    pendingReviews: 0,
    draftsInProgress: 0,
    overdueTasks: 0,
  });
  const [telemetry, setTelemetry] = useState<DynamicTelemetry>({
    cpuUsage: 42,
    memoryUsage: 65,
    networkTraffic: 210,
    sandBoxSecurityStatus: "optimal",
  });

  const [loading, setLoading] = useState(true);
  const [refreshLoading, setRefreshLoading] = useState(false);

  // Theme preference state linked elegantly to DOM token and local persistence
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("theme");
      return saved === null ? true : saved !== "light";
    }
    return true;
  });

  // Modals & Panels toggle
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [notificationPreferencesOpen, setNotificationPreferencesOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // New Project Form state
  const [newProjName, setNewProjName] = useState("");
  const [newProjDesc, setNewProjDesc] = useState("");
  const [newProjLoad, setNewProjLoad] = useState(40);
  const [newProjNodes, setNewProjNodes] = useState(4);
  const [newProjStatus, setNewProjStatus] = useState<Project["status"]>("active");

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.setAttribute("data-theme", "light");
      localStorage.setItem("theme", "light");
    }
  }, [isDarkMode]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 4500);
  };

  // Fetch from in-memory API backend
  const fetchDashboardData = async (isRefetched = false) => {
    if (isRefetched) setRefreshLoading(true);
    try {
      const res = await fetch("/api/dashboard");
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks);
        setProjects(data.projects);
        setNotifications(data.notifications);
        setCalendarEvents(data.calendarEvents);
        setMetrics(data.metrics);
        setTelemetry(data.telemetry);
      }
    } catch (err) {
      console.error("Failed to fetch dashboard telemetry:", err);
      showToast("无法获取系统服务器载荷，请检查后端运行状态。");
    } finally {
      setLoading(false);
      setRefreshLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    // Auto-refresh stats periodically representing active stream
    const interval = setInterval(() => {
      fetchDashboardData();
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  // 1. Task Centers controllers
  const handleToggleTask = async (id: string) => {
    try {
      const res = await fetch(`/api/tasks/${id}/toggle`, { method: "PUT" });
      if (res.ok) {
        fetchDashboardData();
        showToast("任务调度优先级已变更。");
      }
    } catch {
      showToast("变更传输失败。");
    }
  };

  const handleAddTask = async (taskData: { title: string; category: Task["category"]; priority: Task["priority"] }) => {
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(taskData)
      });
      if (res.ok) {
        fetchDashboardData();
        showToast("新安全备份在核心集群部署就绪！");
      }
    } catch {
      showToast("协议部署失效。");
    }
  };

  const handleDeleteTask = async (id: string) => {
    try {
      const res = await fetch(`/api/tasks/${id}`, { method: "DELETE" });
      if (res.ok) {
        fetchDashboardData();
        showToast("已成功撤消该调度任务。");
      }
    } catch {
      showToast("撤消指令未送达。");
    }
  };

  // 2. Project matrix controllers
  const handleAddProject = async (projData: { name: string; description: string; systemLoad: number; coreNodes: number; status?: Project["status"] }) => {
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(projData)
      });
      if (res.ok) {
        fetchDashboardData();
        showToast(`项目节点 [${projData.name}] 成功并入电网矩阵。`);
      }
    } catch {
      showToast("项目创建请求遭阻断。");
    }
  };

  const handleCreateProjectModalSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjName.trim()) return;
    handleAddProject({
      name: newProjName,
      description: newProjDesc,
      systemLoad: newProjLoad,
      coreNodes: newProjNodes,
      status: newProjStatus,
    });
    setNewProjName("");
    setNewProjDesc("");
    setProjectModalOpen(false);
  };

  // 3. Notifications actions
  const handleMarkAllRead = async () => {
    try {
      const res = await fetch("/api/notifications/clear-all", { method: "POST" });
      if (res.ok) {
        fetchDashboardData();
        showToast("全区未读警告日志已清除。");
      }
    } catch {
      showToast("消息清除故障。");
    }
  };

  const handleMarkRead = async (id: string) => {
    try {
      const res = await fetch(`/api/notifications/${id}/read`, { method: "POST" });
      if (res.ok) {
        fetchDashboardData();
      }
    } catch {
      showToast("变更未生效。");
    }
  };

  // 4. Space Calendar actions
  const handleAddEvent = async (eventData: { title: string; date: string; time: string; type: CalendarEvent["type"] }) => {
    try {
      const res = await fetch("/api/calendar/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(eventData)
      });
      if (res.ok) {
        fetchDashboardData();
        showToast(`新事件议程已写入晶闸管 [${eventData.title}]。`);
      }
    } catch {
      showToast("日历写入错误。");
    }
  };

  // 5. Quick Actions logger
  const handleQuickPortalAction = (actionName: string) => {
    showToast(`正在跳转至 [${actionName}] 智能子面板...`);
  };

  // 6. Gemini Core Advisor handshake
  const handleGeminiAnalyze = async (customQuery?: string): Promise<string> => {
    try {
      const res = await fetch("/api/gemini/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customQuery }),
      });
      if (res.ok) {
        const data = await res.json();
        return data.response;
      } else {
        const errData = await res.json();
        if (errData.error === "AI_OFFLINE") {
          return "🚨 PROMETHEUS ADVISOR MODULE OFFLINE // 未配置 API 密钥\n\n请在您的系统设置 (Settings > Secrets) 中配置并绑定您的 `GEMINI_API_KEY`。";
        }
        return `ERROR CODE [500]: Deep neural grid response failure: ${errData.message}`;
      }
    } catch (err) {
      console.error("AI node handshake timeout:", err);
      return "🚨 TERMINAL TRANS-STATION HANDSHAKE FAILURE // 网络路由异常。";
    }
  };

  return (
    <div className="relative min-h-screen bg-[var(--bg-primary)] text-[var(--text-main)] transition-colors duration-300 flex flex-col font-sans cyber-grid selection:bg-cyan-500/30 selection:text-white">
      {/* Absolute sci-fi ambient glows */}
      {isDarkMode && (
        <>
          <div className="absolute top-1/4 left-10 w-96 h-96 bg-purple-500/5 rounded-full blur-[120px] pointer-events-none" />
          <div className="absolute bottom-1/4 right-10 w-96 h-96 bg-cyan-500/5 rounded-full blur-[120px] pointer-events-none" />
        </>
      )}

      {/* Floating System Notification Toast */}
      <AnimatePresence>
        {toastMessage && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            className={`fixed bottom-6 right-6 z-50 p-4 rounded-xl border text-xs font-mono flex items-center gap-3 max-w-sm backdrop-blur-md shadow-2xl ${
              isDarkMode 
                ? "border-cyan-500/30 bg-slate-900/95 text-cyan-300" 
                : "border-cyan-300/60 bg-white/95 text-cyan-800 shadow-[0_10px_30px_rgba(6,182,212,0.15)]"
            }`}
          >
            <div className="p-1 rounded-full bg-cyan-400/15 border border-cyan-400/30 text-cyan-400 animate-pulse">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <span className="font-bold text-shadow-glow uppercase block mb-0.5">&gt; TELEMETRY COM:</span>
              <p className={`font-sans ${isDarkMode ? "text-slate-350" : "text-slate-700"}`}>{toastMessage}</p>
            </div>
            <button
              onClick={() => setToastMessage(null)}
              className="text-slate-500 hover:text-slate-700 ml-auto cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Top Welcome Title Grid Header */}
      {activePage === "dashboard" && (
        <Header
          onOpenNewProject={() => setProjectModalOpen(true)}
          onOpenKnowledgeTrigger={() => showToast("正在调取多维知识拓扑库，加工并解构中...")}
          pendingTasksCount={tasks.filter(t => t.status === "pending").length}
          totalTasksCount={tasks.length}
          isDarkMode={isDarkMode}
          onToggleTheme={() => setIsDarkMode(!isDarkMode)}
          onBackToLanding={() => setActivePage("landing")}
        />
      )}

      {/* Main Core Dashboard Stage Area */}
      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center font-cyber text-cyan-400 animate-pulse gap-3 p-10 select-none">
          <Database className="w-10 h-10 animate-bounce text-cyan-500" />
          <span className="tracking-widest uppercase text-shadow-glow">&gt; INITIALIZING STARDOCK GRID SUB-ELEMENTS...</span>
        </div>
      ) : activePage === "landing" ? (
        <LandingPage
          onEnterDashboard={() => setActivePage("dashboard")}
          isDarkMode={isDarkMode}
          onToggleTheme={() => setIsDarkMode(!isDarkMode)}
          showToast={showToast}
        />
      ) : activePage === "project-detail" ? (
        <ProjectDetailPage
          onBack={() => setActivePage("dashboard")}
          isDarkMode={isDarkMode}
          onAnalyze={handleGeminiAnalyze}
          showToast={showToast}
        />
      ) : (
        <ProjectManagement
          onSelectProject={(projName) => {
            setActivePage("project-detail");
            showToast(`正在解译并初始化 [${projName}] 报告编写及结构工作台...`);
          }}
          onOpenCreateModal={() => setProjectModalOpen(true)}
          isDarkMode={isDarkMode}
          showToast={showToast}
        />
      )}

      {/* Footer System Credits */}
      {activePage !== "landing" && (
        <footer className="border-t border-[var(--border-color)] bg-[var(--bg-tertiary)] py-4 px-6 mt-8 text-center text-[10px] themed-text-muted font-cyber select-none tracking-widest leading-relaxed duration-300">
          PROMETHEUS CONTROL WORKSPACE // SECURITY LEVEL 5SECURED // UTC CHRONOS READY
          <div className="text-[9px] text-slate-500 font-sans mt-0.5">© 2026-PRESENT INTEL TERMINAL GROUP LLC. ALL SYSTEM PROTOCOLS PROTECTED BY STARS SHIELD.</div>
        </footer>
      )}

      {/* CREATE PROJECT DIALOG MODAL */}
      <AnimatePresence>
        {projectModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-md">
            <motion.div
              initial={{ scale: 0.92, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className={`w-full max-w-lg border rounded-xl shadow-2xl p-5 md:p-7 relative font-sans duration-300 ${
                isDarkMode ? "bg-slate-900 border-purple-500/35" : "bg-white border-slate-200"
              }`}
            >
              {/* Corner tech lines */}
              {isDarkMode && <div className="absolute top-0 right-0 w-3 h-3 bg-purple-500/20 clip-corners" />}

              {/* Header */}
              <div className={`flex items-center justify-between border-b pb-3.5 mb-5 ${isDarkMode ? "border-slate-800" : "border-slate-200"}`}>
                <div className="flex items-center gap-2 text-purple-500">
                  <Terminal className="w-5 h-5 animate-pulse" />
                  <h3 className="text-sm font-bold uppercase tracking-wider font-cyber">
                    新建系统项目协议 / Initiate Project Node
                  </h3>
                </div>
                <button
                  onClick={() => setProjectModalOpen(false)}
                  className={`p-1 rounded-md transition-colors cursor-pointer ${
                    isDarkMode ? "text-slate-400 hover:text-white hover:bg-slate-800" : "text-slate-550 hover:text-slate-900 hover:bg-slate-100"
                  }`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Form content */}
              <form onSubmit={handleCreateProjectModalSubmit} className="flex flex-col gap-4 text-xs font-sans">
                <div>
                  <label className={`block font-bold mb-1.5 ${isDarkMode ? "text-slate-400" : "text-slate-700"}`}>项目系统标识 / Project Name</label>
                  <input
                    type="text"
                    required
                    value={newProjName}
                    onChange={e => setNewProjName(e.target.value)}
                    placeholder="例如: 智能舆情遥测解译网..."
                    className={`w-full rounded-lg px-3 py-2 outline-none transition-colors ${
                      isDarkMode 
                        ? "bg-slate-950 border border-slate-700 text-slate-200 focus:border-purple-500" 
                        : "bg-slate-50 border border-slate-300 text-slate-900 focus:border-purple-500 focus:bg-white"
                    }`}
                  />
                </div>

                <div>
                  <label className={`block font-bold mb-1.5 ${isDarkMode ? "text-slate-400" : "text-slate-700"}`}>核心任务概要 / Description</label>
                  <textarea
                    rows={3}
                    value={newProjDesc}
                    onChange={e => setNewProjDesc(e.target.value)}
                    placeholder="输入运行参数，协议需求和高维矩阵指标..."
                    className={`w-full rounded-lg px-3 py-2 outline-none transition-colors ${
                      isDarkMode 
                        ? "bg-slate-950 border border-slate-700 text-slate-200 focus:border-purple-500" 
                        : "bg-slate-50 border border-slate-300 text-slate-900 focus:border-purple-500 focus:bg-white"
                    }`}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={`block font-bold mb-1.5 ${isDarkMode ? "text-slate-400" : "text-slate-700"}`}>分配系统流载荷 (%)</label>
                    <input
                      type="number"
                      required
                      min={10}
                      max={100}
                      value={newProjLoad}
                      onChange={e => setNewProjLoad(parseInt(e.target.value))}
                      className={`w-full rounded-lg px-3 py-2 outline-none transition-colors ${
                        isDarkMode 
                          ? "bg-slate-950 border border-slate-700 text-slate-200" 
                          : "bg-slate-50 border border-slate-300 text-slate-900"
                      }`}
                    />
                  </div>

                  <div>
                    <label className={`block font-bold mb-1.5 ${isDarkMode ? "text-slate-400" : "text-slate-700"}`}>配备群核节点数</label>
                    <input
                      type="number"
                      required
                      min={1}
                      max={128}
                      value={newProjNodes}
                      onChange={e => setNewProjNodes(parseInt(e.target.value))}
                      className={`w-full rounded-lg px-3 py-2 outline-none transition-colors ${
                        isDarkMode 
                          ? "bg-slate-950 border border-slate-700 text-slate-200" 
                          : "bg-slate-50 border border-slate-300 text-slate-900"
                      }`}
                    />
                  </div>
                </div>

                <div>
                  <label className={`block font-bold mb-1.5 ${isDarkMode ? "text-slate-400" : "text-slate-700"}`}>启动状态属性 / Core Status</label>
                  <select
                    value={newProjStatus}
                    onChange={e => setNewProjStatus(e.target.value as Project["status"])}
                    className={`w-full rounded-lg px-3 py-1.5 outline-none cursor-pointer ${
                      isDarkMode 
                        ? "bg-slate-950 border border-slate-700 text-slate-200" 
                        : "bg-slate-50 border border-slate-300 text-slate-900"
                    }`}
                  >
                    <option value="active">运行中 (Active)</option>
                    <option value="review">待审核评估 (Review)</option>
                    <option value="paused">冷休眠冷存储 (Paused)</option>
                  </select>
                </div>

                {/* Footer submit */}
                <div className={`flex items-center justify-end gap-3 border-t pt-4 mt-2 ${isDarkMode ? "border-slate-800" : "border-slate-200"}`}>
                  <button
                    type="button"
                    onClick={() => setProjectModalOpen(false)}
                    className={`px-4 py-2 cursor-pointer hover:underline ${isDarkMode ? "text-slate-400 hover:text-white" : "text-slate-600 hover:text-slate-900"}`}
                  >
                    取消协议
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2.5 bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 text-white font-bold rounded-lg border border-purple-400/20 shadow-lg cursor-pointer flex items-center gap-1.5 hover:shadow-purple-500/20 active:opacity-95"
                  >
                    <Check className="w-4 h-4" />
                    <span>核准项目并启动调度</span>
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
