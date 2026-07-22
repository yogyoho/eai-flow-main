/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import { 
  Sparkles, Rocket, BookOpen, Settings, Layout, Database, Network, 
  ShieldCheck, ArrowRight, CheckCircle2, ChevronRight, Activity, Zap,
  Globe, FileCode, Server, RefreshCw, Layers, Check, Star, Play, Search, Code
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

interface LandingPageProps {
  onEnterDashboard: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
  showToast: (msg: string) => void;
}

export default function LandingPage({
  onEnterDashboard,
  isDarkMode,
  onToggleTheme,
  showToast
}: LandingPageProps) {
  // Navigation active menu link state for high-fidelity header interaction
  const [activeMenu, setActiveMenu] = useState<"engineering" | "knowledge" | "docs" | "settings">("engineering");

  // Local interaction states for detail popups / simulators
  const [activePortal, setActivePortal] = useState<string | null>(null);

  // Search state inside mockup
  const [searchQuery, setSearchQuery] = useState("");

  const handleQuickPortalClick = (portal: string) => {
    setActivePortal(portal);
    showToast(`正在装载 [${portal}] 核心微内核，双向物理网格分析已发起...`);
  };

  // Preseeded mock entities for Entity Graph Browser
  const mockEntities = [
    { id: "ent-1", label: "煤岩坚固性指数 (f)", type: "数值指标", sec: "设计规范 规范 2.1.2", code: "COAL_hardness_index" },
    { id: "ent-2", label: "主加氢环网阀门", type: "物料装备", sec: "防灾布局 4.2", code: "VALVE_H2_MAIN" },
    { id: "ent-3", label: "可燃探头灵敏阈", type: "遥测因子", sec: "安全监控 5.6", code: "SENS_GAS_LEAK" },
    { id: "ent-4", label: "采煤工作面防突", type: "高爆隐患", sec: "灾害预防 1.3", code: "PREVENT_OUTBURST" }
  ];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] text-[var(--text-main)] font-sans flex flex-col relative overflow-hidden transition-colors duration-350 cyber-grid">
      
      {/* BACKGROUND SCI-FI AMBIENCE GLOWS */}
      <div className="absolute top-[-10%] left-[-20%] w-[60%] h-[60%] bg-[rgba(6,182,212,0.06)] rounded-full blur-[160px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-20%] w-[50%] h-[50%] bg-[rgba(139,92,246,0.05)] rounded-full blur-[140px] pointer-events-none" />

      {/* UPPER LOGOHEADER SECTION */}
      <header className="sticky top-0 z-40 bg-[var(--header-bg)] border-b border-[var(--border-color-muted)] backdrop-blur-md px-4 md:px-12 py-4 flex items-center justify-between transition-all duration-300">
        
        {/* Left Side: Logo of Beijing Huayu */}
        <div className="flex items-center gap-3 cursor-pointer group" onClick={() => setActivePortal(null)}>
          <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center shadow-[0_0_12px_rgba(37,99,235,0.45)] group-hover:scale-105 transition-transform duration-300">
            <Globe className="w-5 h-5 text-white animate-spin-slow" />
          </div>
          <div>
            <span className="text-base font-extrabold tracking-wide bg-gradient-to-r from-blue-600 via-cyan-500 to-indigo-600 bg-clip-text text-transparent">
              北京华宇工程有限公司
            </span>
            <p className="text-[9px] text-slate-500 font-cyber tracking-widest mt-0.5">BEIJING HUAYU ENGINEERING</p>
          </div>
        </div>

        {/* Center: Navigation Menu links matching image precisely */}
        <nav className="hidden md:flex items-center gap-8 text-[13px] font-sans font-bold text-slate-500 dark:text-slate-400">
          <button 
            onClick={() => { setActiveMenu("engineering"); onEnterDashboard(); }}
            className={`transition-colors hover:text-blue-500 flex items-center gap-1.5 cursor-pointer ${activeMenu === "engineering" ? "text-blue-600 dark:text-blue-400 font-bold text-shadow-glow" : ""}`}
          >
            工程报告
          </button>
          
          <button 
            onClick={() => { setActiveMenu("knowledge"); handleQuickPortalClick("知识库"); }}
            className={`transition-colors hover:text-blue-500 flex items-center gap-1.5 cursor-pointer ${activeMenu === "knowledge" ? "text-blue-600 dark:text-blue-400 font-bold" : ""}`}
          >
            知识工厂
          </button>
          
          <button 
            onClick={() => { setActiveMenu("docs"); handleQuickPortalClick("模板中心"); }}
            className={`transition-colors hover:text-blue-500 flex items-center gap-1.5 cursor-pointer ${activeMenu === "docs" ? "text-blue-600 dark:text-blue-400 font-bold" : ""}`}
          >
            文档空间
          </button>
          
          <button 
            onClick={() => { setActiveMenu("settings"); handleQuickPortalClick("设置"); }}
            className={`transition-colors hover:text-blue-500 flex items-center gap-1.5 cursor-pointer ${activeMenu === "settings" ? "text-blue-600 dark:text-blue-400 font-bold" : ""}`}
          >
            设置
          </button>
        </nav>

        {/* Right Side Theme Switcher & Profile element */}
        <div className="flex items-center gap-4">
          
          {/* Cyber Accent Indicator LED */}
          <div className="hidden lg:flex items-center gap-2 px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-cyber text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span>ALIVE SEC_ACCESS</span>
          </div>

          {/* Theme toggler */}
          <button 
            onClick={onToggleTheme} 
            className="p-1.5 rounded-lg border border-[var(--border-color-muted)] text-[var(--text-muted)] hover:text-cyan-500 hover:border-cyan-500/30 transition-all cursor-pointer"
            title="切换主题"
          >
            {isDarkMode ? "☀" : "🌙"}
          </button>

          {/* User profile avatar matching image circular design */}
          <div className="w-8 h-8 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-505 dark:text-blue-400 flex items-center justify-center font-bold text-xs ring-2 ring-blue-500/5 hover:ring-blue-500/25 cursor-pointer transition-all">
            华
          </div>
        </div>
      </header>

      {/* CORE WRAPPER SCALING CONTAINER */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-12 py-8 md:py-16 flex flex-col gap-12 md:gap-20">
        
        {/* UPPER HERO SECTION GRID (LEFT INFO CONTENT, RIGHT BENTO STAT CARDS) */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-8 md:gap-12 items-center">
          
          {/* HERO LEFT COLUMN info content */}
          <div className="lg:col-span-7 flex flex-col gap-6 text-left items-start">
            
            {/* 1. Cyber Chip Banner */}
            <motion.div 
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="px-4 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/25 text-blue-600 dark:text-blue-450 text-[11px] font-sans font-bold tracking-wide flex items-center gap-1.5 shadow-[0_0_15px_rgba(59,130,246,0.1)] self-start"
            >
              <Sparkles className="w-3.5 h-3.5 text-blue-500 animate-pulse" />
              <span>企业智能体平台套件，融合知识工厂与RAG知识库</span>
            </motion.div>

            {/* 2. Headline - Mega Display pairing */}
            <div className="flex flex-col gap-4">
              <motion.h1 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.1 }}
                className="text-3xl md:text-5xl font-extrabold tracking-tight text-[var(--text-main)] leading-[1.15] font-sans"
              >
                北京华宇工程：煤炭设计领域
                <span className="block mt-2 bg-gradient-to-r from-blue-600 via-cyan-500 to-indigo-600 bg-clip-text text-transparent pb-1">
                  智能应用平台
                </span>
              </motion.h1>

              {/* Gradient cyan/blue bar precisely matching the design line */}
              <motion.div 
                initial={{ scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: 0.8, delay: 0.3 }}
                className="h-[4px] w-full max-w-[480px] bg-gradient-to-r from-blue-600 via-cyan-400 to-transparent rounded origin-left"
              />
            </div>

            {/* 3. Subdescription */}
            <motion.p 
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="text-sm md:text-base text-slate-500 dark:text-slate-400 font-mono tracking-wide leading-relaxed"
            >
              统一编排 Agent、知识库、skills、MCP与工具链
            </motion.p>

            {/* 4. Action buttons bar */}
            <motion.div 
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="flex items-center gap-4 flex-wrap mt-2"
            >
              {/* Primary: 开始写作 */}
              <button
                onClick={onEnterDashboard}
                className="px-6 py-3.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm tracking-wider flex items-center gap-2 cursor-pointer shadow-lg hover:shadow-[0_0_20px_rgba(37,99,235,0.35)] transition-all group duration-300"
              >
                <Rocket className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                <span>开始写作</span>
              </button>

              {/* Secondary: 知识加工 */}
              <button
                onClick={() => handleQuickPortalClick("知识库")}
                className="px-6 py-3.5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border-color)] hover:border-purple-500/40 hover:bg-purple-500/5 text-[var(--text-main)] font-semibold text-sm tracking-wider flex items-center gap-2 cursor-pointer transition-all duration-300"
              >
                <BookOpen className="w-4 h-4 text-purple-400" />
                <span>知识加工</span>
              </button>
            </motion.div>

          </div>

          {/* HERO RIGHT BENTO GRID (4 SCIFI METRICS CARDS WITH BEAUTIFUL HOVERS) */}
          <div className="lg:col-span-5 grid grid-cols-1 sm:grid-cols-2 gap-4 lg:pl-4">
            
            {/* Bento Card 1: 知识量 (Star icon inside circular glow, with soft border glow as in image) */}
            <motion.div 
              whileHover={{ y: -4 }}
              className="p-5 border border-blue-500/25 bg-blue-500/5 dark:bg-blue-950/10 rounded-2xl flex flex-col justify-between gap-4 transition-all duration-300 shadow-[0_5px_15px_rgba(37,99,235,0.06)] ring-1 ring-blue-500/10 hover:border-blue-500/50"
            >
              <div className="w-10 h-10 rounded-xl bg-blue-500/15 border border-blue-500/20 flex items-center justify-center text-blue-500">
                <Star className="w-5 h-5 fill-blue-500/20" />
              </div>
              <div>
                <div className="text-3xl font-black font-cyber text-blue-600 dark:text-blue-400 tracking-tight">2300+</div>
                <div className="text-xs font-bold text-[var(--text-main)] mt-1">知识量</div>
                <div className="text-[10px] text-slate-500 font-sans mt-1 group-hover:text-slate-400">业务人员的参与与支持</div>
              </div>
            </motion.div>

            {/* Bento Card 2: SKILLS数量 */}
            <motion.div 
              whileHover={{ y: -4 }}
              className="p-5 border border-[var(--border-color-muted)] hover:border-purple-500/30 bg-slate-400/5 hover:bg-slate-400/10 rounded-2xl flex flex-col justify-between gap-4 transition-all duration-300"
            >
              <div className="w-10 h-10 rounded-xl bg-purple-500/15 border border-purple-500/20 flex items-center justify-center text-purple-500">
                <Check className="w-5 h-5" />
              </div>
              <div>
                <div className="text-3xl font-black font-cyber text-purple-600 dark:text-purple-400 tracking-tight">200+</div>
                <div className="text-xs font-bold text-[var(--text-main)] mt-1">SKILLS数量</div>
                <div className="text-[10px] text-slate-500 font-sans mt-1">持续改进和问题解决能力</div>
              </div>
            </motion.div>

            {/* Bento Card 3: MCP数量 */}
            <motion.div 
              whileHover={{ y: -4 }}
              className="p-5 border border-[var(--border-color-muted)] hover:border-indigo-500/30 bg-slate-400/5 hover:bg-slate-400/10 rounded-2xl flex flex-col justify-between gap-4 transition-all duration-300"
            >
              <div className="w-10 h-10 rounded-xl bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center text-indigo-500">
                <Network className="w-5 h-5" />
              </div>
              <div>
                <div className="text-3xl font-black font-cyber text-indigo-600 dark:text-indigo-400 tracking-tight">50+</div>
                <div className="text-xs font-bold text-[var(--text-main)] mt-1">MCP数量</div>
                <div className="text-[10px] text-slate-500 font-sans mt-1">活跃的开发迭代和功能更新</div>
              </div>
            </motion.div>

            {/* Bento Card 4: 报告种类 */}
            <motion.div 
              whileHover={{ y: -4 }}
              className="p-5 border border-[var(--border-color-muted)] hover:border-cyan-500/35 bg-slate-400/5 hover:bg-slate-400/10 rounded-2xl flex flex-col justify-between gap-4 transition-all duration-300"
            >
              <div className="w-10 h-10 rounded-xl bg-cyan-500/15 border border-cyan-500/20 flex items-center justify-center text-cyan-500">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <div className="text-3xl font-black font-cyber text-cyan-600 dark:text-cyan-400 tracking-tight">10+</div>
                <div className="text-xs font-bold text-[var(--text-main)] mt-1">报告种类</div>
                <div className="text-[10px] text-slate-500 font-sans mt-1">煤炭行业工程设计类报告生成</div>
              </div>
            </motion.div>

          </div>

        </section>

        {/* INTERACTIVE COMPONENT POPUPS DISPLAY AREA */}
        <AnimatePresence>
          {activePortal && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="w-full"
            >
              <div className="p-6 md:p-8 rounded-2xl border border-blue-500/30 bg-blue-500/5 backdrop-blur-md relative overflow-hidden flex flex-col gap-5">
                
                {/* Visual grid in widget */}
                <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-blue-500/15 to-transparent rounded-bl-full" />
                
                {/* Upper line */}
                <div className="flex items-center justify-between border-b border-blue-500/20 pb-3">
                  <div className="flex items-center gap-2">
                    <Zap className="w-4 h-4 text-blue-500 animate-pulse" />
                    <span className="text-[11px] font-cyber tracking-widest text-blue-500 uppercase">
                      PORTAL_HYPER_LINK INITIATED // {activePortal}
                    </span>
                  </div>
                  <button 
                    onClick={() => setActivePortal(null)}
                    className="p-1 rounded bg-blue-500/10 text-blue-500 hover:bg-blue-500/25 transition-colors cursor-pointer text-xs font-bold px-2"
                  >
                    CLOSE [X]
                  </button>
                </div>

                {/* Sub-panels inside portal based on what was selected */}
                {activePortal === "知识库" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <h4 className="text-base font-bold text-[var(--text-main)] font-sans flex items-center gap-1.5">
                        华宇智能知识工厂 (Huayu Knowledge Factory)
                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                      </h4>
                      <p className="text-xs text-slate-500 font-normal leading-relaxed mt-2">
                        知识管理中枢已加载。支持跨采掘深度、选煤设计准则、矿井水处理规程等多维度 RAG 数据。您可以直接在此提交设计文档，或关联现有的国家一级和地方安全标准库。
                      </p>
                      <div className="relative mt-4">
                        <input 
                          type="text"
                          placeholder="搜索行业知识、国家标准、采掘规范..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color)] px-3.5 py-2 rounded-xl text-xs focus:ring-1 focus:ring-blue-500 focus:border-blue-500/60 transition-all text-[var(--text-main)] outline-none"
                        />
                        <Search className="w-3.5 h-3.5 text-slate-500 absolute right-3.5 top-2.5" />
                      </div>
                    </div>
                    
                    <div className="flex flex-col gap-2.5 bg-slate-400/5 p-4 rounded-xl border border-[var(--border-color-muted)]">
                      <span className="text-[10px] text-slate-500 font-cyber">LATEST COMPILED SPECIFICATIONS</span>
                      <div className="flex flex-col gap-2">
                        <div className="p-2 bg-[var(--bg-primary)] rounded-lg text-xs flex justify-between border border-[var(--border-color-muted)]">
                          <span>GB 50215-2015 煤炭工业矿井设计规范</span>
                          <span className="text-emerald-500 font-cyber">已同步</span>
                        </div>
                        <div className="p-2 bg-[var(--bg-primary)] rounded-lg text-xs flex justify-between border border-[var(--border-color-muted)]">
                          <span>GB 50414-2018 煤矿安全规程图解</span>
                          <span className="text-emerald-500 font-cyber">已同步</span>
                        </div>
                        <button 
                          onClick={() => showToast("正在向集群拉取更多最新设计规范，请稍候...")}
                          className="text-[11px] text-blue-500 font-semibold cursor-pointer hover:underline self-start mt-1 flex items-center gap-1"
                        >
                          导入本地设计专篇 (PPTX/PDF) <ArrowRight className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {activePortal === "实体类型库" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <h4 className="text-base font-bold text-[var(--text-main)] font-sans">
                        元实体拓扑浏览器 (Metaclass Entity Browser)
                      </h4>
                      <p className="text-xs text-slate-500 font-normal leading-relaxed mt-1">
                        分析煤矿开采工艺中实体词条、特征变量与地质要素的网络关联。将非结构化工控记录转换为高精实体图谱。
                      </p>
                      
                      <div className="mt-4 flex flex-wrap gap-2">
                        {mockEntities.map(ent => (
                          <div 
                            key={ent.id}
                            className="px-2.5 py-1.5 rounded-lg bg-[var(--bg-primary)] border border-blue-500/15 hover:border-blue-500/40 cursor-pointer transition-all text-xs flex flex-col"
                            onClick={() => showToast(`已锁定实体: ${ent.label} (代码: ${ent.code})`)}
                          >
                            <span className="font-bold text-[var(--text-main)] mb-0.5">{ent.label}</span>
                            <span className="text-[9px] text-slate-500 font-cyber uppercase">{ent.type} · {ent.sec}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="bg-[var(--bg-tertiary)] rounded-xl border border-[var(--border-color-muted)] p-4 flex flex-col justify-between">
                      <div>
                        <span className="text-[10px] text-slate-500 font-cyber uppercase block mb-1">REAL-TIME TELEMETRY GRAPH</span>
                        <div className="h-20 flex items-end gap-1.5 justify-center py-2 border-b border-blue-500/10">
                          <div className="w-3 h-[25%] bg-blue-500/30 rounded-t" />
                          <div className="w-3 h-[45%] bg-blue-500/45 rounded-t" />
                          <div className="w-3 h-[90%] bg-blue-500 rounded-t animate-pulse" />
                          <div className="w-3 h-[60%] bg-cyan-400 rounded-t" />
                          <div className="w-3 h-[75%] bg-purple-500 rounded-t" />
                        </div>
                      </div>
                      <div className="flex justify-between items-center text-[10px] font-cyber text-slate-550 mt-2">
                        <span>ENTITIES COMPILING: 593 NODES</span>
                        <span className="text-emerald-500">STATUS: RE-SHIELD_OK</span>
                      </div>
                    </div>
                  </div>
                )}

                {activePortal === "采购管理" && (
                  <div className="flex flex-col gap-3">
                    <h4 className="text-sm font-bold text-[var(--text-main)] flex items-center gap-1.5">
                      <Layers className="w-4 h-4 text-purple-500" />
                      煤炭设备及备件材料采购集成 (Procurement & Sourcing Link)
                    </h4>
                    <p className="text-xs text-slate-500 leading-relaxed max-w-2xl">
                      已连接至大同煤电及神华神东物资采空保障系统。智能提取工程报告中的设备材料备忘录，包括皮带输送机、防爆配电装置及瓦斯监控主机等，一键生成采购草案。
                    </p>
                    <div className="flex gap-3 mt-1 flex-wrap">
                      <button 
                        onClick={() => showToast("智能提取工作流已触发，正在分析辽阳石化与宁煤项目装备明细。")}
                        className="px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold cursor-pointer transition-colors"
                      >
                        提取报告内装备明细
                      </button>
                      <button 
                        onClick={() => showToast("已启动山西阳泰采购清单仿真协议。")}
                        className="px-3.5 py-1.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)] hover:border-purple-500/20 text-xs font-bold cursor-pointer text-[var(--text-main)] transition-colors"
                      >
                        拉取山西矿用高低压开关柜模板
                      </button>
                    </div>
                  </div>
                )}

                {activePortal === "模板中心" && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-3 bg-[var(--bg-primary)] rounded-xl border border-[var(--border-color-muted)] flex flex-col justify-between hover:border-blue-500/15 transition-colors">
                      <div>
                        <span className="text-[10px] text-blue-500 font-cyber">TEMPLATE #001</span>
                        <h5 className="text-xs font-bold text-[var(--text-main)] mt-1">矿井防火防突出设计编制</h5>
                      </div>
                      <button 
                        onClick={() => { onEnterDashboard(); showToast("已导入矿井防火防突出设计专篇模板，立即进入写作。"); }}
                        className="text-[11px] text-blue-500 hover:underline text-left mt-3 font-semibold"
                      >
                        选用此模板 →
                      </button>
                    </div>

                    <div className="p-3 bg-[var(--bg-primary)] rounded-xl border border-[var(--border-color-muted)] flex flex-col justify-between hover:border-blue-500/15 transition-colors">
                      <div>
                        <span className="text-[10px] text-purple-400 font-cyber">TEMPLATE #002</span>
                        <h5 className="text-xs font-bold text-[var(--text-main)] mt-1">智能综采工作面技改专篇</h5>
                      </div>
                      <button 
                        onClick={() => { onEnterDashboard(); showToast("已导入智能综采工作面技改专篇，立即进入写作。"); }}
                        className="text-[11px] text-purple-400 hover:underline text-left mt-3 font-semibold"
                      >
                        选用此模板 →
                      </button>
                    </div>

                    <div className="p-3 bg-[var(--bg-primary)] rounded-xl border border-[var(--border-color-muted)] flex flex-col justify-between hover:border-blue-500/15 transition-colors">
                      <div>
                        <span className="text-[10px] text-cyan-400 font-cyber">TEMPLATE #003</span>
                        <h5 className="text-xs font-bold text-[var(--text-main)] mt-1">辽阳石化改建防火高危险专篇</h5>
                      </div>
                      <button 
                        onClick={() => { onEnterDashboard(); showToast("正在载入辽阳石化改建防火高危险专篇（2026版）。"); }}
                        className="text-[11px] text-cyan-400 hover:underline text-left mt-3 font-semibold"
                      >
                        选用此模板 →
                      </button>
                    </div>
                  </div>
                )}

                {activePortal === "设置" && (
                  <div className="p-3 bg-[var(--bg-primary)] rounded-xl border border-[var(--border-color-muted)]">
                    <h5 className="text-xs font-bold mb-2">服务配置节点 (System Service Nodes)</h5>
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center justify-between p-2 bg-[var(--bg-secondary)] rounded border border-transparent hover:border-slate-500/10 text-xs">
                        <span>Prometheus 心智内核推理引擎</span>
                        <span className="text-emerald-500 font-cyber">极速配置中 (ONLINE)</span>
                      </div>
                      <div className="flex items-center justify-between p-2 bg-[var(--bg-secondary)] rounded border border-transparent hover:border-slate-500/10 text-xs">
                        <span>Websocket 协同实时锁管理器</span>
                        <button 
                          onClick={() => showToast("协同锁已校验重置")}
                          className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-450 hover:bg-blue-500/20 text-[10px]"
                        >
                          重新校验
                        </button>
                      </div>
                    </div>
                  </div>
                )}

              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* LOWER SECTION: QUICK ACCESS ("快速访问") */}
        <section className="flex flex-col gap-8 md:gap-10 border-t border-[var(--border-color-muted)] pt-12 md:pt-16">
          
          {/* Section labels */}
          <div className="flex flex-col items-center text-center gap-2">
            <h2 className="text-2xl md:text-3xl font-extrabold tracking-tight text-[var(--text-main)] font-sans">
              快速访问
            </h2>
            <p className="text-xs md:text-sm text-slate-500 font-sans tracking-wide">
              探索平台核心功能模块
            </p>
          </div>

          {/* Quick Access Cards, 5 items grid matching the mockup */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5">
            
            {/* Cell 1: Dashboard (Linked to actual internal dashboard transition) */}
            <motion.div 
              whileHover={{ y: -3, scale: 1.01 }}
              onClick={onEnterDashboard}
              className="p-5 border border-[var(--border-color-muted)] bg-slate-400/5 hover:bg-slate-400/10 rounded-2xl group transition-all duration-300 cursor-pointer flex items-center justify-between gap-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center flex-shrink-0">
                  <Activity className="w-5 h-5" />
                </div>
                <div className="min-w-0 text-left">
                  <h3 className="text-sm font-extrabold text-[var(--text-main)] font-sans group-hover:text-blue-500 transition-colors">
                    Dashboard
                  </h3>
                  <p className="text-[10px] text-slate-500 font-mono tracking-wider mt-0.5">/dashboard</p>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-slate-500 group-hover:translate-x-1 transition-transform" />
            </motion.div>

            {/* Cell 2: 知识库 (With folder icon etc) */}
            <motion.div 
              whileHover={{ y: -3, scale: 1.01 }}
              onClick={() => handleQuickPortalClick("知识库")}
              className="p-5 border border-[var(--border-color-muted)] bg-slate-400/5 hover:bg-slate-400/10 rounded-2xl group transition-all duration-300 cursor-pointer flex items-center justify-between gap-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-505 dark:text-indigo-400 flex items-center justify-center flex-shrink-0">
                  <BookOpen className="w-5 h-5" />
                </div>
                <div className="min-w-0 text-left">
                  <h3 className="text-sm font-extrabold text-[var(--text-main)] font-sans group-hover:text-indigo-555 dark:group-hover:text-indigo-400 transition-colors">
                    知识库
                  </h3>
                  <p className="text-[10px] text-slate-500 font-mono tracking-wider mt-0.5">/knowledge</p>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-slate-500 group-hover:translate-x-1 transition-transform" />
            </motion.div>

            {/* Cell 3: 采购管理 */}
            <motion.div 
              whileHover={{ y: -3, scale: 1.01 }}
              onClick={() => handleQuickPortalClick("采购管理")}
              className="p-5 border border-[var(--border-color-muted)] bg-slate-400/5 hover:bg-slate-400/10 rounded-2xl group transition-all duration-300 cursor-pointer flex items-center justify-between gap-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-500 flex items-center justify-center flex-shrink-0">
                  <Layers className="w-5 h-5" />
                </div>
                <div className="min-w-0 text-left">
                  <h3 className="text-sm font-extrabold text-[var(--text-main)] font-sans group-hover:text-purple-500 transition-colors">
                    采购管理
                  </h3>
                  <p className="text-[10px] text-slate-500 font-mono tracking-wider mt-0.5">/procurement</p>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-slate-500 group-hover:translate-x-1 transition-transform" />
            </motion.div>

            {/* Cell 4: 模板中心 */}
            <motion.div 
              whileHover={{ y: -3, scale: 1.01 }}
              onClick={() => handleQuickPortalClick("模板中心")}
              className="p-5 border border-[var(--border-color-muted)] bg-slate-400/5 hover:bg-slate-400/10 rounded-2xl group transition-all duration-300 cursor-pointer flex items-center justify-between gap-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-cyan-500/10 text-cyan-500 flex items-center justify-center flex-shrink-0">
                  <Code className="w-5 h-5" />
                </div>
                <div className="min-w-0 text-left">
                  <h3 className="text-sm font-extrabold text-[var(--text-main)] font-sans group-hover:text-cyan-500 transition-colors">
                    模板中心
                  </h3>
                  <p className="text-[10px] text-slate-500 font-mono tracking-wider mt-0.5">/knowledge/templates</p>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-slate-500 group-hover:translate-x-1 transition-transform" />
            </motion.div>

            {/* Cell 5: 实体类型库 (With beautiful glowing blue border as in image) */}
            <motion.div 
              whileHover={{ y: -3, scale: 1.01 }}
              onClick={() => handleQuickPortalClick("实体类型库")}
              className="p-5 border border-blue-500/40 bg-blue-500/5 rounded-2xl group transition-all duration-300 cursor-pointer flex items-center justify-between gap-4 shadow-[0_0_15px_rgba(6,182,212,0.15)] ring-1 ring-blue-500/20"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center flex-shrink-0">
                  <Database className="w-5 h-5" />
                </div>
                <div className="min-w-0 text-left">
                  <h3 className="text-sm font-extrabold text-[var(--text-main)] font-sans group-hover:text-blue-500 cursor-pointer transition-colors">
                    实体类型库
                  </h3>
                  <p className="text-[10px] text-blue-500 font-mono tracking-wider mt-0.5">/entity-types</p>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-blue-500 group-hover:translate-x-1 transition-transform" />
            </motion.div>

          </div>

        </section>

      </main>

      {/* SOLID DARK BLACK/CHARCOAL FOOTER PRECISELY MATCHING LOGOIMAGE BOTTOM */}
      <footer className="w-full bg-slate-950 text-slate-500 border-t border-slate-900 py-8 px-4 text-center text-xs tracking-wider transition-colors duration-300">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 px-4 md:px-8">
          <span>© 北京华宇工程有限公司 2026 v0.5.0</span>
          <div className="flex items-center gap-4 text-[10px] font-cyber text-slate-600">
            <span>SECURE SYSTEM PROT_LAYER OK</span>
            <span>•</span>
            <span>MCP PROTOCOLS ENABLED</span>
          </div>
        </div>
      </footer>

    </div>
  );
}
