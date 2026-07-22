/**
 * @license
 * SPDX-License-Identifier: Apache-2.5
 */

import React, { useState, useMemo } from "react";
import { 
  FolderGit, Layers, Search, Plus, List, Grid, User, Calendar, 
  BookOpen, Users, ShieldAlert, Sparkles, Filter, ChevronRight, 
  HelpCircle, Building2, Terminal, CheckCircle2, RotateCw, RefreshCw
} from "lucide-react";
import { Project } from "../types.js";
import { motion, AnimatePresence } from "motion/react";

// Richer mock project interface specifically matching user screenshot fields
interface HighFidelityProject {
  id: string;
  name: string;
  category: "全部" | "煤炭挖掘" | "矿产勘查" | "采购管理" | "公用工程";
  status: "active" | "review" | "paused" | "completed";
  subCategoryText: string;
  owner: string;
  date: string;
  chaptersCount: number;
  membersCount: number;
  department?: string;
  progress: number;
}

interface ProjectManagementProps {
  onSelectProject: (name: string) => void;
  onOpenCreateModal: () => void;
  isDarkMode: boolean;
  showToast: (msg: string) => void;
}

export default function ProjectManagement({
  onSelectProject,
  onOpenCreateModal,
  isDarkMode,
  showToast
}: ProjectManagementProps) {
  
  // Real initial set of high fidelity projects matching user's exact uploaded image list
  const [dbProjects, setDbProjects] = useState<HighFidelityProject[]>([
    {
      id: "proj-hf-1",
      name: "页面测试2-验证上下文注入",
      category: "公用工程",
      status: "active",
      subCategoryText: "fire_protection_design · 公用工程_消防设计专篇_分析报告_E2E",
      owner: "Administrator",
      date: "2026/06/22",
      chaptersCount: 34,
      membersCount: 1,
      department: "共用工程室",
      progress: 60
    },
    {
      id: "proj-hf-2",
      name: "页面测试-消防专篇",
      category: "公用工程",
      status: "active",
      subCategoryText: "fire_protection_design · 公用工程_消防设计专篇_2026_高危防灾",
      owner: "Administrator",
      date: "2026/06/22",
      chaptersCount: 34,
      membersCount: 1,
      department: "共用工程室",
      progress: 75
    },
    {
      id: "proj-hf-3",
      name: "抚顺石化新装置建设消防设计专篇",
      category: "公用工程",
      status: "active",
      subCategoryText: "fire_protection_design · 公用工程_消防设计专篇_现场实测",
      owner: "李四",
      date: "2026/06/22",
      chaptersCount: 34,
      membersCount: 3,
      department: "共用工程室",
      progress: 45
    },
    {
      id: "proj-exc-1",
      name: "神东哈拉沟采区瓦斯抽排与防突技术专项",
      category: "煤炭挖掘",
      status: "completed",
      subCategoryText: "coal_excavation_design · 煤层安全开采监控_高突保护",
      owner: "王五",
      date: "2026/05/18",
      chaptersCount: 28,
      membersCount: 5,
      department: "开采规准室",
      progress: 100
    },
    {
      id: "proj-min-1",
      name: "华阳一矿深部煤炭地质勘查三维构造解译",
      category: "矿产勘查",
      status: "review",
      subCategoryText: "mineral_exploration · 物探磁法反演与水平地层断层分析",
      owner: "张强",
      date: "2026/06/10",
      chaptersCount: 15,
      membersCount: 2,
      department: "勘查物探中心",
      progress: 90
    },
    {
      id: "proj-proc-1",
      name: "阳煤集团采煤机备件及刮板输送机智审采购案",
      category: "采购管理",
      status: "active",
      subCategoryText: "procurement_sourcing · 矿山综采成套设备保障核算",
      owner: "赵敏",
      date: "2026/06/15",
      chaptersCount: 12,
      membersCount: 4,
      department: "物资采购科",
      progress: 30
    }
  ]);

  // Filters & layout modes matching the screenshot
  const [selectedCategory, setSelectedCategory] = useState<HighFidelityProject["category"] | "全部">("全部");
  const [searchQuery, setSearchQuery] = useState("");
  const [layoutMode, setLayoutMode] = useState<"grid" | "list">("grid");

  // Filter projects dynamically
  const filteredProjects = useMemo(() => {
    return dbProjects.filter(p => {
      const matchCategory = selectedCategory === "全部" ? true : p.category === selectedCategory;
      const matchSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          p.subCategoryText.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          p.owner.toLowerCase().includes(searchQuery.toLowerCase());
      return matchCategory && matchSearch;
    });
  }, [dbProjects, selectedCategory, searchQuery]);

  // Compute stats matching the 4 metrics cards at top of screenshot
  const stats = useMemo(() => {
    const total = dbProjects.length;
    const active = dbProjects.filter(p => p.status === "active").length;
    const review = dbProjects.filter(p => p.status === "review").length;
    const completed = dbProjects.filter(p => p.status === "completed").length;
    return { total, active, review, completed };
  }, [dbProjects]);

  return (
    <div className="flex-1 w-full bg-[var(--bg-primary)] text-[var(--text-main)] font-sans px-4 md:px-12 py-6 flex flex-col gap-8 transition-all duration-300 relative">
      
      {/* 1. UPPER HEADER PANEL (Matching precisely Logo title, search and create button) */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[var(--border-color-muted)] pb-4">
        
        {/* Left Side: Portfolio Title with Document Icon inside violet circle */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/25 flex items-center justify-center text-purple-600 dark:text-purple-400 shadow-[0_0_12px_rgba(147,51,234,0.15)]">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-[var(--text-main)] font-sans">
              项目管理
            </h1>
            <p className="text-[10px] text-slate-500 font-mono tracking-widest mt-0.5 uppercase">Project Workspace Coordinator</p>
          </div>
        </div>

        {/* Right Side: Interactive Search and Create Project Button */}
        <div className="flex items-center gap-3 flex-wrap">
          
          {/* Magnifying search input bar exactly style-matched */}
          <div className="relative min-w-[240px]">
            <input 
              type="text" 
              placeholder="搜索项目..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border-color)] hover:border-blue-500/30 px-3.5 py-2 pl-9 rounded-xl text-xs focus:ring-1 focus:ring-blue-500 focus:border-blue-500/60 transition-all text-[var(--text-main)] outline-none"
            />
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
          </div>

          <motion.button
            whileHover={{ scale: 1.02, y: -0.5 }}
            whileTap={{ scale: 0.98 }}
            onClick={onOpenCreateModal}
            className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold font-sans tracking-wide flex items-center gap-1.5 shadow-[0_3px_12px_rgba(37,99,235,0.25)] hover:shadow-[0_0_15px_rgba(37,99,235,0.4)] cursor-pointer transition-all duration-300"
          >
            <Plus className="w-4 h-4 text-white" />
            <span>新建项目</span>
          </motion.button>

        </div>

      </div>

      {/* 2. DYNAMIC QUANTUM PORTFOLIO KPI GRID (Precise rendering of top metric cards) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* Metric Card 1: 全部项目 */}
        <motion.div
          whileHover={{ y: -2 }}
          className="p-4 rounded-xl border border-[var(--border-color-muted)] hover:border-blue-500/30 bg-slate-450/5 lg:bg-[var(--bg-secondary)] flex items-center gap-4 transition-all duration-300"
        >
          <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/15 flex items-center justify-center text-blue-600 dark:text-blue-400">
            <FolderGit className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs text-slate-500 dark:text-slate-400 font-bold block">全部项目</span>
            <span className="text-2xl font-black font-cyber text-[var(--text-main)] mt-0.5">{stats.total}</span>
          </div>
        </motion.div>

        {/* Metric Card 2: 进行中 */}
        <motion.div
          whileHover={{ y: -2 }}
          className="p-4 rounded-xl border border-blue-500/25 bg-blue-500/5 flex items-center gap-4 transition-all duration-300 shadow-[0_4px_12px_rgba(59,130,246,0.05)]"
        >
          <div className="w-12 h-12 rounded-xl bg-blue-500/20 border border-blue-500/25 flex items-center justify-center text-blue-600 dark:text-blue-400">
            <BookOpen className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <span className="text-xs text-blue-650 dark:text-blue-400 font-bold block">进行中</span>
            <span className="text-2xl font-black font-cyber text-blue-600 dark:text-blue-400 mt-0.5">{stats.active}</span>
          </div>
        </motion.div>

        {/* Metric Card 3: 审批中 */}
        <motion.div
          whileHover={{ y: -2 }}
          className="p-4 rounded-xl border border-[var(--border-color-muted)] hover:border-amber-500/30 bg-slate-450/5 lg:bg-[var(--bg-secondary)] flex items-center gap-4 transition-all duration-300"
        >
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/15 flex items-center justify-center text-amber-550 dark:text-amber-400">
            <RotateCw className="w-6 h-6 animate-spin-slow" />
          </div>
          <div>
            <span className="text-xs text-slate-500 dark:text-slate-400 font-bold block">审批中</span>
            <span className="text-2xl font-black font-cyber text-[var(--text-main)] mt-0.5">{stats.review}</span>
          </div>
        </motion.div>

        {/* Metric Card 4: 已完成 */}
        <motion.div
          whileHover={{ y: -2 }}
          className="p-4 rounded-xl border border-[var(--border-color-muted)] hover:border-emerald-500/30 bg-slate-450/5 lg:bg-[var(--bg-secondary)] flex items-center gap-4 transition-all duration-300"
        >
          <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/15 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs text-slate-500 dark:text-slate-400 font-bold block">已完成</span>
            <span className="text-2xl font-black font-cyber text-[var(--text-main)] mt-0.5">{stats.completed}</span>
          </div>
        </motion.div>

      </div>

      {/* 3. MIDDLE BAR: CATEGORY TABS & LAYOUT CONTROLLERS */}
      <div className="flex items-center justify-between gap-4 border-b border-[var(--border-color-muted)] pb-2 flex-wrap">
        
        {/* Left Side: Filter Tabs identical to image */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {(["全部", "煤炭挖掘", "矿产勘查", "采购管理", "公用工程"] as const).map((cat) => (
            <button
              key={cat}
              onClick={() => {
                setSelectedCategory(cat);
                showToast(`已筛选类别: ${cat}`);
              }}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                selectedCategory === cat
                  ? "bg-blue-600 text-white font-black shadow-md shadow-blue-500/10"
                  : "text-slate-550 hover:text-blue-500 hover:bg-slate-400/5 bg-transparent border border-transparent"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Right Side: Grid / List View Toggle Switch */}
        <div className="flex items-center gap-1 p-0.5 bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-color-muted)]">
          
          {/* Grid Layout Switch */}
          <button
            onClick={() => setLayoutMode("grid")}
            className={`p-1.5 rounded-md cursor-pointer transition-colors ${layoutMode === "grid" ? "bg-white dark:bg-slate-800 text-blue-500 shadow-sm" : "text-slate-500 hover:text-[var(--text-main)]"}`}
            title="网格视图"
          >
            <Grid className="w-4 h-4" />
          </button>

          {/* List Layout Switch */}
          <button
            onClick={() => setLayoutMode("list")}
            className={`p-1.5 rounded-md cursor-pointer transition-colors ${layoutMode === "list" ? "bg-white dark:bg-slate-800 text-blue-500 shadow-sm" : "text-slate-500 hover:text-[var(--text-main)]"}`}
            title="列表视图"
          >
            <List className="w-4 h-4" />
          </button>

        </div>

      </div>

      {/* 4. MAIN BODY CONTAINER: DYNAMIC CO-WORKING PROJECT ITEMS BLOCK */}
      <AnimatePresence mode="popLayout">
        {filteredProjects.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="py-16 text-center border border-dashed border-[var(--border-color)] rounded-2xl flex flex-col items-center justify-center bg-[var(--bg-secondary)]"
          >
            <FolderGit className="w-12 h-12 text-slate-400 mb-2 animate-bounce" />
            <h3 className="text-sm font-bold text-slate-500">未检索到匹配项目</h3>
            <p className="text-[10px] text-slate-500 font-mono mt-1">NO ACTIVE PROJECT NODES FOUND MATCHING SEARCH FILTERS</p>
          </motion.div>
        ) : layoutMode === "grid" ? (
          
          // GRID VIEW EXACT TO PROTOTYPE
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
          >
            {filteredProjects.map((proj, idx) => (
              <motion.div
                key={proj.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: idx * 0.05 }}
                whileHover={{ y: -4 }}
                onClick={() => {
                  onSelectProject(proj.name);
                  showToast(`成功对接并载入项目架构 [${proj.name}] 主控制台...`);
                }}
                className="themed-card rounded-xl border border-[var(--border-color-muted)] hover:border-blue-500/40 bg-slate-400/5 hover:bg-slate-400/10 cursor-pointer transition-all duration-300 relative overflow-hidden flex flex-col group shadow-sm hover:shadow-[0_8px_30px_rgba(37,99,235,0.08)] ring-1 ring-blue-500/5"
              >
                
                {/* Visual Accent Corner Glow */}
                <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-br from-blue-500/10 to-transparent rounded-bl-full pointer-events-none transition-opacity opacity-0 group-hover:opacity-100 duration-300" />
                
                {/* Upper Module Info Area */}
                <div className="p-5 flex flex-col gap-3.5 flex-1 text-left">
                  
                  {/* Top line block: Portfolio Badge and Title */}
                  <div className="flex items-start gap-3">
                    
                    {/* Blue Icon Folder Unit with chinese character '项' matching mockup screen */}
                    <div className="w-10 h-10 rounded-xl bg-blue-600/10 border border-blue-500/25 text-blue-600 dark:text-blue-400 flex items-center justify-center font-black text-sm flex-shrink-0 relative">
                      <span>项</span>
                      <div className="absolute bottom-[-2px] right-[-2px] w-2.5 h-2.5 rounded-full bg-blue-500 border border-white dark:border-slate-900 group-hover:scale-110 transition-transform" />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1.5 flex-wrap">
                        <h3 className="text-sm font-extrabold text-[var(--text-main)] group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors tracking-wide leading-snug line-clamp-2">
                          {proj.name}
                        </h3>
                        
                        {/* Status Label matching prototype exactly */}
                        <span className={`px-2.5 py-0.5 rounded text-[9px] font-black uppercase tracking-wider ${
                          proj.status === "active" ? "bg-blue-500/10 text-blue-500 border border-blue-500/20" :
                          proj.status === "review" ? "bg-amber-500/10 text-amber-500 border border-amber-500/20" :
                          proj.status === "completed" ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20" :
                          "bg-slate-100 text-slate-500 border border-slate-200"
                        }`}>
                          {proj.status === "active" ? "进行中" :
                           proj.status === "review" ? "待审核" : 
                           proj.status === "completed" ? "已完成" : "in_progress"}
                        </span>
                      </div>

                      {/* Tag descriptors */}
                      <p className="text-[10px] text-slate-500 hover:text-slate-400 transition-colors mt-1 font-mono tracking-wide line-clamp-1">
                        {proj.subCategoryText}
                      </p>
                    </div>

                  </div>

                  {/* Meta items Grid Rows matching images */}
                  <div className="grid grid-cols-2 gap-y-2.5 gap-x-2 border-t border-[var(--border-color-muted)] pt-3.5 text-xs text-slate-500">
                    
                    {/* Administrator Metadata */}
                    <div className="flex items-center gap-1.5 min-w-0">
                      <User className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                      <span className="truncate">{proj.owner}</span>
                    </div>

                    {/* Date Metadata */}
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Calendar className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                      <span className="truncate font-mono">{proj.date}</span>
                    </div>

                    {/* Chapters count list */}
                    <div className="flex items-center gap-1.5 col-span-2">
                      <BookOpen className="w-3.5 h-3.5 text-slate-400" />
                      <span>{proj.chaptersCount} 章节已初始化编写</span>
                    </div>

                  </div>

                </div>

                {/* Separated solid bottom info bar matching prototype exactly list view */}
                <div className="p-3 border-t border-[var(--border-color-muted)] bg-slate-400/2.5 group-hover:bg-slate-450/5 flex items-center justify-between text-xs text-slate-500 transition-colors duration-200">
                  <div className="flex items-center gap-1.5">
                    <Users className="w-3.5 h-3.5 text-slate-400" />
                    <span>{proj.membersCount} 名成员</span>
                  </div>

                  {/* Horizontal progress representation line inside card */}
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden relative">
                      <div 
                        className="h-full bg-blue-500 group-hover:bg-blue-400 transition-all duration-500"
                        style={{ width: `${proj.progress}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono font-bold text-slate-500">{proj.progress}%</span>
                  </div>
                </div>

              </motion.div>
            ))}
          </motion.div>
        ) : (
          
          // LIST VIEW PRECISE COMPILATION
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col gap-3.5"
          >
            {filteredProjects.map((proj, idx) => (
              <motion.div
                key={proj.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25, delay: idx * 0.04 }}
                onClick={() => {
                  onSelectProject(proj.name);
                  showToast(`对接项目并拉取规范协议 [${proj.name}]...`);
                }}
                className="p-4 rounded-xl border border-[var(--border-color-muted)] hover:border-blue-500/35 bg-slate-400/5 hover:bg-slate-400/10 cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all duration-200 shadow-sm"
              >
                
                {/* Left Side elements: name tags and avatar */}
                <div className="flex items-center gap-4.5 min-w-0 flex-1">
                  
                  <div className="w-9 h-9 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-extrabold text-xs flex-shrink-0">
                    项
                  </div>

                  <div className="min-w-0 text-left">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-bold text-[var(--text-main)] truncate tracking-wide">
                        {proj.name}
                      </h3>
                      <span className="text-[10px] text-slate-500 font-mono px-2 py-0.5 rounded border border-[var(--border-color-muted)]">
                        {proj.category}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 font-mono tracking-wide truncate mt-1">
                      {proj.subCategoryText}
                    </p>
                  </div>

                </div>

                {/* Right Side metadata rows structured for clean responsive display */}
                <div className="flex items-center gap-6 text-xs text-slate-500 flex-wrap md:flex-nowrap">
                  
                  {/* Owner */}
                  <div className="flex items-center gap-1.5 min-w-[100px]">
                    <User className="w-3.5 h-3.5 text-slate-400" />
                    <span>{proj.owner}</span>
                  </div>

                  {/* Chapters */}
                  <div className="flex items-center gap-1.5 min-w-[70px]">
                    <BookOpen className="w-3.5 h-3.5 text-slate-400" />
                    <span>{proj.chaptersCount} 章节</span>
                  </div>

                  {/* Members count */}
                  <div className="flex items-center gap-1.5 min-w-[70px]">
                    <Users className="w-3.5 h-3.5 text-slate-400" />
                    <span>{proj.membersCount} 成员</span>
                  </div>

                  {/* Status */}
                  <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${
                    proj.status === "active" ? "bg-blue-500/10 text-blue-500 border border-blue-500/15" :
                    proj.status === "review" ? "bg-amber-500/10 text-amber-500 border border-amber-500/15" :
                    "bg-emerald-500/10 text-emerald-500 border border-emerald-500/15"
                  }`}>
                    {proj.status === "active" ? "进行中" : "待处理"}
                  </span>

                  {/* Micro indicator arrow */}
                  <ChevronRight className="w-4 h-4 text-slate-400 hidden md:block" />

                </div>

              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* 5. BOTTOM EXTRA SCI-FI CHIPS OR STATUS LAYER */}
      <div className="flex items-center justify-between text-[11px] font-cyber text-slate-500 border-t border-[var(--border-color-muted)] pt-5">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-blue-500 animate-pulse" />
          <span>PORTFOLIO KERNEL PROTOCOLS LOADED</span>
        </div>
        <div className="flex items-center gap-4 text-slate-500">
          <span>ALERTS: 0 DISRUPTIONS</span>
          <span>•</span>
          <span className="text-emerald-500 font-bold">SYNCHRONIZED WITH BEIJING DATACENTER</span>
        </div>
      </div>

    </div>
  );
}
