/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import { 
  ArrowLeft, Users, FileText, BarChart3, Layers, Calendar, 
  Settings, MessageSquare, Plus, Trash2, CheckCircle2, ChevronRight, 
  SlidersHorizontal, LayoutGrid, ListFilter, Play, Sparkles, Send, 
  RotateCw, Save, ShieldAlert, Cpu, Check, Terminal, FileCode, CheckSquare, Edit3, X
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";

interface Member {
  id: string;
  name: string;
  role: "负责人" | "成员";
  avatarColor: string;
}

interface Chapter {
  id: string;
  title: string;
  status: "pending" | "writing" | "reviewing" | "completed";
  assignee: string;
  progress: number; // percentage (e.g. 229% as in prototype)
  timeAgo: string;
  content: string;
  sectionNumber: string;
  parentId?: string;
}

interface ProjectDetailPageProps {
  onBack: () => void;
  isDarkMode: boolean;
  onAnalyze: (customQuery?: string) => Promise<string>;
  showToast: (msg: string) => void;
}

export default function ProjectDetailPage({
  onBack,
  isDarkMode,
  onAnalyze,
  showToast,
}: ProjectDetailPageProps) {
  // Navigation / Tab state within project: 'overview' | 'editor' | 'review'
  const [activeSubTab, setActiveSubTab] = useState<"overview" | "editor" | "review">("overview");
  
  // Layout mode state: 'list' (大纲列表) | 'kanban' (看板模式)
  const [layoutMode, setLayoutMode] = useState<"list" | "kanban">("list");

  // Filter state for status
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "writing" | "reviewing" | "completed">("all");

  // Quick State for members (preseeded with screenshot values)
  const [members, setMembers] = useState<Member[]>([
    { id: "1", name: "lisi", role: "负责人", avatarColor: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
    { id: "2", name: "wanger", role: "成员", avatarColor: "bg-purple-500/10 text-purple-500 border-purple-500/20" },
    { id: "3", name: "zhaoliu", role: "成员", avatarColor: "bg-cyan-500/10 text-cyan-500 border-cyan-500/20" },
  ]);

  const [showAddMember, setShowAddMember] = useState(false);
  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberRole, setNewMemberRole] = useState<"负责人" | "成员">("成员");

  // Preseeded 34 chapters matching structure
  const [chapters, setChapters] = useState<Chapter[]>([
    // Group 1: 设计依据及采用的标准
    {
      id: "c1",
      sectionNumber: "1",
      title: "设计依据及采用的标准",
      status: "completed",
      assignee: "zhaoliu",
      progress: 100,
      timeAgo: "7天前",
      content: "本章主要阐述辽阳石化改扩建项目涉及的全部设计法律、行政法规。依据《中华人民共和国安全生产法》、《中华人民共和国消防法》、《建设工程安全生产管理条例》等文件，对各工艺装置火灾危险等级进行科学划分与安全防护等级设定。"
    },
    {
      id: "c1-1",
      parentId: "c1",
      sectionNumber: "1.1",
      title: "设计依据",
      status: "completed",
      assignee: "zhaoliu",
      progress: 229, // 229% word count ratio/target word count matched as per prototype
      timeAgo: "7天前",
      content: "改扩建项目整体遵照中国石油天然气集团公司安全标准进行深化。针对新建重整反应器与循环氢压缩机厂房，配套安装可燃气体泄漏远程光纤感知监测系统及多路超细多级泡沫喷洒干道。依托原有工艺地块，重新核验三级防火红线距离。"
    },
    {
      id: "c1-2",
      parentId: "c1",
      sectionNumber: "1.2",
      title: "设计采用的技术标准、规范",
      status: "completed",
      assignee: "wanger",
      progress: 327, // 327% as in prototype
      timeAgo: "7天前",
      content: "严密参考国家强制执行规范：《中华人民共和国消防法》、《建设设计防火规范》(GB 50016-2014) 2018版、《石油化工企业设计防火标准》(GB 50160-2008) 2015版、《石油天然气工程设计防火规范》(GB 50183-2004) 等。引入抗震防爆防静电安全接地矩阵标准。"
    },
    {
      id: "c1-3",
      parentId: "c1",
      sectionNumber: "1.3",
      title: "地方相关法规",
      status: "completed",
      assignee: "zhaoliu",
      progress: 214, // 214% as in prototype
      timeAgo: "7天前",
      content: "遵照辽宁省与辽阳市特种化工项目防灾法规细则。对高含硫原油接卸作业、脱硫加氢精制等关键区域，专门设置防静电、高敏可燃感知预警，配备由消防中控直接控制的水炮射流列阵，全天候实施气象因子和工艺压力热力耦合监控。"
    },
    // Group 2: 概述
    {
      id: "c2",
      sectionNumber: "2",
      title: "概述",
      status: "completed",
      assignee: "wanger",
      progress: 100,
      timeAgo: "7天前",
      content: "总体梳理本次辽阳石化E2E最终报告的全部装置构成与投资规模。本章涵盖工程建设地址、总体规划、主装置处理负荷、辅助公用系统、主要安全隐患源与对策，确保工业园绿色和长周期零泄漏稳态健康运行。"
    },
    {
      id: "c2-1",
      parentId: "c2",
      sectionNumber: "2.1",
      title: "项目位置",
      status: "completed",
      assignee: "zhaoliu",
      progress: 180,
      timeAgo: "7天前",
      content: "项目选址位于辽宁省辽阳市宏伟区辽阳石化产业园区。宏观地形平坦开阔，周边配套公路网完善。工程所选用工艺边界距离居民区直线安全距离均超过1.5公里。地基属稳定抗震岩性组分，处于微降水带，极少受偶发地质形变灾害侵扰。"
    },
    {
      id: "c2-2",
      parentId: "c2",
      sectionNumber: "2.2",
      title: "项目建设功能定位",
      status: "completed",
      assignee: "zhaoliu",
      progress: 195,
      timeAgo: "7天前",
      content: "旨在打造年产220万吨芳烃与炼油核心承载网。建设涉及重整工艺段的高效抗风抗爆外围结构，及超高压蒸汽闭路联产。以全流程网络流化分析系统（Grid-Telemetry）实现原料接收、加氢精制、重核芳烃组分切分段的跨单元秒级智能调优。"
    },
    {
      id: "c2-3",
      parentId: "c2",
      sectionNumber: "2.3",
      title: "建设规模",
      status: "completed",
      assignee: "zhaoliu",
      progress: 150,
      timeAgo: "7天前",
      content: "期初处理规模为1200万吨/年常减压蒸馏和220万吨连续重整。新建油气二级冷凝回放回收系统及工艺废水微弧氧化净化设施。公用配电网最大承载280MW，主备回路以微波和千兆光纤进行神经链路握手，确保断电极限状态阀门智能自锁。"
    },
    {
      id: "c2-4",
      parentId: "c2",
      sectionNumber: "2.4",
      title: "建设内容",
      status: "completed",
      assignee: "wanger",
      progress: 240,
      timeAgo: "7天前",
      content: "主要包含加氢反应炉群配置、高精馏分离塔建设、储运罐区防漫溢浮盘升级，及配套应急高密度消防给水泵站。主站设置3台高功率混流柴油水泵，双管路自锁连通运行。设置消防数字双胞胎仿真屏幕以开展全物理场景预案仿真。"
    },
    // Adding some writeable chapters to represent progress variety
    {
      id: "c3",
      sectionNumber: "3",
      title: "消防给水系统总体布局",
      status: "reviewing",
      assignee: "lisi",
      progress: 85,
      timeAgo: "2小时前",
      content: "针对高危危化品灌区，正在构建闭路水雾环向网。由应急供水泵房、中继管网及自锁消防高位罐共同构成。该系统可在35秒内将超高压消防水注满高危裂解区并形成环状泡沫覆盖。"
    },
    {
      id: "c4",
      sectionNumber: "4",
      title: "可燃气体智能防壁解译",
      status: "writing",
      assignee: "lisi",
      progress: 42,
      timeAgo: "刚刚",
      content: "此部分正在由AI初稿初筛完毕，进入人工重写精修。我们将在此设计覆盖整个一期工艺界区的高速激光吸收遥测探头。利用多维度光谱识别技术，能在一秒内检测万分之一级的氢气或丁二烯泄漏并联动关闭切断阀。"
    },
  ]);

  // Create filler state to make the total chapters count exactly 34 as shown in the screenshot
  const totalChaptersCount = 34;
  const completedChaptersCount = chapters.filter(c => c.status === "completed").length;
  // We can treat our visible chapters list plus some virtual entries to equal 34 in UI metrics!

  // Editor and active selection states
  const [selectedChapterId, setSelectedChapterId] = useState<string>("c1-1");
  const activeChapter = chapters.find(c => c.id === selectedChapterId) || chapters[0];

  // Forms and chat within Project
  const [activeChapterContent, setActiveChapterContent] = useState<string>(activeChapter.content);

  // Sync content editor state when switching items
  React.useEffect(() => {
    if (activeChapter) {
      setActiveChapterContent(activeChapter.content);
    }
  }, [selectedChapterId]);

  // AI Chat sidebar slide-out state
  const [aiChatOpen, setAiChatOpen] = useState(false);
  const [aiMessages, setAiMessages] = useState<Array<{ sender: "ai" | "user"; text: string; time: string }>>([
    { sender: "ai", text: "您好！我是希尔德智能报告助手 (Hildegard Copilot)。已成功加载项目 [辽阳石化-E2E最终] 的专业规范文件。请问有什么需要我帮您编写、润色或校验的？", time: "上午 10:24" }
  ]);
  const [aiInput, setAiInput] = useState("");
  const [aiChatLoading, setAiChatLoading] = useState(false);

  // Triggering document revisions
  const [isSaving, setIsSaving] = useState(false);
  const [revisionHistory, setRevisionHistory] = useState<Array<{ id: string; user: string; rev: string; time: string }>>([
    { id: "1", user: "lisi", rev: "初始初稿创建", time: "2026-06-15 11:22" },
    { id: "2", user: "wanger", rev: "更新了1.2技术标准参数", time: "2026-06-18 15:40" },
  ]);

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!aiInput.trim() || aiChatLoading) return;

    const userMsg = aiInput;
    const nowStr = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    
    setAiMessages(prev => [...prev, { sender: "user", text: userMsg, time: nowStr }]);
    setAiInput("");
    setAiChatLoading(true);

    try {
      // Proxy through real gemini backend to have fully smart contextual answering
      const apiResponse = await onAnalyze(`基于项目【辽阳石化-E2E最终】的消防、防灾报告设计情景：用户提问：${userMsg}`);
      setAiMessages(prev => [...prev, { sender: "ai", text: apiResponse, time: nowStr }]);
    } catch {
      setAiMessages(prev => [...prev, { sender: "ai", text: "【系统通信异常】无法接入 Prometheus 决策心智核，请稍后重试运行。", time: nowStr }]);
    } finally {
      setAiChatLoading(false);
    }
  };

  // AI Co-writer direct helper triggers (e.g. Expand, Polish, Audit)
  const handleAiAssistMode = async (mode: "expand" | "polish" | "audit") => {
    setIsSaving(true);
    let promptText = "";
    if (mode === "expand") {
      promptText = `针对章节【${activeChapter.sectionNumber} ${activeChapter.title}】的当前内容：\n"${activeChapterContent}"\n请帮我大幅扩写它的化工设计专有名词和安全余量分析，使其更为严密详细，符合《石油化工企业设计防火标准》。`;
    } else if (mode === "polish") {
      promptText = `针对章节【${activeChapter.sectionNumber} ${activeChapter.title}】的当前内容：\n"${activeChapterContent}"\n请帮我润色优化其技术词汇，使其更精炼、更具有科技感和专业国家规范风格。`;
    } else {
      promptText = `针对章节【${activeChapter.sectionNumber} ${activeChapter.title}】的当前内容：\n"${activeChapterContent}"\n请指出可能遗漏的消防危险化学品规范和隐患漏洞检测机制。`;
    }

    try {
      const response = await onAnalyze(promptText);
      if (mode === "audit") {
        // Show an overlay/toast or inject audit comments
        setAiMessages(prev => [
          ...prev, 
          { sender: "ai", text: `【大纲安全审视报告 - ${activeChapter.sectionNumber}】：\n\n${response}`, time: "当前" }
        ]);
        setAiChatOpen(true);
      } else {
        // Directly update active text content representing cybernetic synthesis
        setActiveChapterContent(prev => `${prev}\n\n【智能协同生产输出】：\n${response}`);
        
        // Show toast style info
        setAiMessages(prev => [
          ...prev, 
          { sender: "ai", text: `我已为【${activeChapter.title}】章节完成了智能${mode === "expand" ? "扩写" : "润色"}，内容已写入编辑器中，请您审阅并保存。`, time: "当前" }
        ]);
      }
    } catch {
      // fallback
      setActiveChapterContent(prev => prev + `\n\n[协作终端信号受阻：未配置有效的高级神经网络，内容通过常态缓存保护]`);
    } finally {
      setIsSaving(false);
    }
  };

  // Safe saving function
  const handleSaveActiveChapter = () => {
    setIsSaving(true);
    setTimeout(() => {
      setChapters(prev => prev.map(c => {
        if (c.id === selectedChapterId) {
          return {
            ...c,
            content: activeChapterContent,
            progress: Math.min(c.progress + Math.floor(Math.random() * 20) + 15, 395), // dynamically shift progress up as they save new edits
            timeAgo: "刚刚"
          };
        }
        return c;
      }));

      // Append new revision history node
      setRevisionHistory(prev => [
        {
          id: String(prev.length + 1),
          user: "负责人(lisi)",
          rev: `修改 ${activeChapter.sectionNumber} 字词微量修正`,
          time: new Date().toISOString().replace('T', ' ').substring(0, 16)
        },
        ...prev
      ]);

      setIsSaving(false);
    }, 800);
  };

  const handleAddMemberSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemberName.trim()) return;

    const newMember: Member = {
      id: String(members.length + 1),
      name: newMemberName.trim().toLowerCase(),
      role: newMemberRole,
      avatarColor: newMemberRole === "负责人" 
        ? "bg-blue-500/10 text-blue-500 border-blue-500/20" 
        : "bg-purple-500/10 text-purple-500 border-purple-500/20"
    };

    setMembers(prev => [...prev, newMember]);
    setNewMemberName("");
    setShowAddMember(false);
  };

  const handleDeleteMember = (id: string, name: string) => {
    if (members.length <= 1) {
      alert("项目中必须保留至少一名项目人员。");
      return;
    }
    setMembers(prev => prev.filter(m => m.id !== id));
  };

  // Calculated Metrics
  const activeChaptersCount = chapters.filter(c => c.status === "writing" || c.status === "reviewing").length;
  // Format character count
  const fileCharCount = chapters.reduce((sum, c) => sum + c.content.length * 12, 18500).toLocaleString(); // synthetic word count math

  // Filtered Chapters based on top Segment clicks
  const filteredChapters = chapters.filter(c => {
    if (statusFilter === "all") return true;
    return c.status === statusFilter;
  });

  return (
    <div className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-8 py-6 flex flex-col gap-6 font-sans">
      
      {/* 1. TOP BREATHING CYBER-HEADER METADATA */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[var(--border-color-muted)] pb-4">
        
        {/* Left Project Tag Info */}
        <div className="flex items-center gap-3">
          <button 
            onClick={onBack}
            className="p-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] text-[var(--text-muted)] hover:text-cyan-500 hover:border-cyan-500/35 transition-all cursor-pointer flex items-center justify-center group"
          >
            <ArrowLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          </button>
          
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xl font-bold tracking-tight text-[var(--text-main)] font-sans">
                辽阳石化-E2E最终
              </h2>
              <span className="text-[10px] uppercase font-cyber px-2.5 py-0.5 rounded border border-blue-500/30 bg-blue-500/10 text-blue-400 font-bold tracking-widest">
                fire_protection_design
              </span>
              <span className="text-[10px] font-sans px-2 py-0.5 rounded bg-purple-500/15 border border-purple-500/20 text-purple-600 dark:text-purple-400 font-bold">
                负责人
              </span>
            </div>
            <p className="text-[11px] text-slate-500 font-mono mt-1">
              创建于: 2026年6月15日 <span className="mx-1.5">•</span> 上次同步: 15:52:23 <span className="mx-1.5">•</span> 新增 0 个文件
            </p>
          </div>
        </div>

        {/* Right sub-navigation Tabs */}
        <div className="flex items-center gap-2 bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] p-1 rounded-xl scrollbar-none overflow-x-auto">
          <button
            onClick={() => setActiveSubTab("overview")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeSubTab === "overview" 
                ? "bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.3)]" 
                : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-slate-400/5"
            }`}
          >
            项目概览
          </button>
          
          <button
            onClick={() => setActiveSubTab("editor")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1 ${
              activeSubTab === "editor" 
                ? "bg-purple-600 text-white shadow-[0_0_10px_rgba(147,51,234,0.3)]" 
                : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-slate-400/5"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>文档编辑</span>
          </button>

          <button
            onClick={() => setActiveSubTab("review")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1 ${
              activeSubTab === "review" 
                ? "bg-teal-600 text-white shadow-[0_0_10px_rgba(13,148,136,0.3)]" 
                : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-slate-400/5"
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>审核工作台</span>
          </button>

          <div className="h-4 w-[1px] bg-[var(--border-color-muted)] mx-1" />

          {/* Enter Dialogue Button */}
          <button
            onClick={() => setAiChatOpen(!aiChatOpen)}
            className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-500 font-sans border border-blue-400/20 text-white flex items-center gap-1.5 transition-all shadow-md group cursor-pointer"
          >
            <MessageSquare className="w-3.5 h-3.5 animate-pulse group-hover:scale-110 transition-transform" />
            <span>进入对话</span>
          </button>
        </div>

      </div>

      {/* 2. STATS OVERVIEW CARDS (4 ROW BLOCKS AS SHOWN IN SCREENSHOT) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* Card 1: 活跃章节 */}
        <div className="border border-blue-500/15 bg-blue-500/5 dark:bg-blue-950/10 rounded-xl p-4 flex flex-col justify-between group hover:scale-[1.015] transition-all relative overflow-hidden">
          <div className="absolute top-0 right-0 w-2 h-2 bg-blue-500/10" />
          <div className="flex items-center justify-between gap-2.5">
            <span className="text-xs font-bold text-[var(--text-main)]">活跃章节</span>
            <div className="p-1 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-505 dark:text-blue-400">
              <Layers className="w-4 h-4 animate-pulse" />
            </div>
          </div>
          <div className="my-2 text-3xl font-extrabold font-cyber text-blue-600 dark:text-blue-400 text-shadow-glow">
            {activeChaptersCount}/{totalChaptersCount}
          </div>
          <p className="text-[10px] text-slate-500 font-mono tracking-wider">编写中 / CYBERNETIC CO-WRITING</p>
        </div>

        {/* Card 2: 成员数 */}
        <div className="border border-purple-500/15 bg-purple-500/5 dark:bg-purple-950/10 rounded-xl p-4 flex flex-col justify-between group hover:scale-[1.015] transition-all relative overflow-hidden">
          <div className="absolute top-0 right-0 w-2 h-2 bg-purple-500/10" />
          <div className="flex items-center justify-between gap-2.5">
            <span className="text-xs font-bold text-[var(--text-main)]">成员数</span>
            <div className="p-1 rounded-md bg-purple-500/10 border border-purple-500/20 text-purple-505 dark:text-purple-400">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <div className="my-2 text-3xl font-extrabold font-cyber text-purple-600 dark:text-purple-400">
            {members.length}
          </div>
          <p className="text-[10px] text-slate-500 font-mono tracking-wider">ACTIVE RESEARCHERS</p>
        </div>

        {/* Card 3: 文件数 */}
        <div className="border border-cyan-500/15 bg-cyan-500/5 dark:bg-cyan-950/10 rounded-xl p-4 flex flex-col justify-between group hover:scale-[1.015] transition-all relative overflow-hidden">
          <div className="absolute top-0 right-0 w-2 h-2 bg-cyan-500/10" />
          <div className="flex items-center justify-between gap-2.5">
            <span className="text-xs font-bold text-[var(--text-main)]">文件数</span>
            <div className="p-1 rounded-md bg-cyan-500/10 border border-cyan-500/20 text-cyan-505 dark:text-cyan-400">
              <FileCode className="w-4 h-4" />
            </div>
          </div>
          <div className="my-2 text-3xl font-extrabold font-cyber text-cyan-600 dark:text-cyan-400">
            1
          </div>
          <p className="text-[10px] text-slate-500 font-mono tracking-wider">COMPILED DOSSIERS</p>
        </div>

        {/* Card 4: 已写字数 */}
        <div className="border border-amber-500/15 bg-amber-500/5 dark:bg-amber-950/10 rounded-xl p-4 flex flex-col justify-between group hover:scale-[1.015] transition-all relative overflow-hidden">
          <div className="absolute top-0 right-0 w-2 h-2 bg-amber-500/10" />
          <div className="flex items-center justify-between gap-2.5">
            <span className="text-xs font-bold text-[var(--text-main)]">已写字数</span>
            <div className="p-1 rounded-md bg-amber-500/10 border border-amber-500/20 text-amber-505 dark:text-amber-400">
              <FileText className="w-4 h-4" />
            </div>
          </div>
          <div className="my-2 text-2xl md:text-3xl font-extrabold font-cyber text-amber-600 dark:text-amber-400">
            {fileCharCount}
          </div>
          <p className="text-[10px] text-slate-500 font-mono tracking-wider">累计 / ACCUMULATIVE GLYPHS</p>
        </div>

      </div>

      {/* 3. DYNAMIC STATUS LEGEND SCANNERS (待编写 | 编写中 | 审核中 | 已完成) */}
      <div className="themed-card rounded-xl p-3 flex flex-wrap items-center justify-between gap-4 text-xs font-cyber border-[var(--border-color-muted)] duration-300">
        
        {/* Legend buttons which acts as filters */}
        <div className="flex items-center gap-4 flex-wrap">
          <button 
            onClick={() => setStatusFilter(statusFilter === "pending" ? "all" : "pending")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
              statusFilter === "pending" 
                ? "bg-slate-400/20 border-slate-500 text-slate-350" 
                : "border-transparent text-slate-500 hover:text-[var(--text-main)] hover:bg-slate-400/5"
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500 ring-2 ring-slate-500/15" />
            <span>待编写</span>
            <span className="font-bold font-sans px-1 rounded bg-slate-500/10 text-slate-400 text-[10px]">
              {chapters.filter(c => c.status === "pending").length}
            </span>
          </button>

          <button 
            onClick={() => setStatusFilter(statusFilter === "writing" ? "all" : "writing")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
              statusFilter === "writing" 
                ? "bg-blue-500/10 border-blue-500/30 text-blue-500" 
                : "border-transparent text-slate-500 hover:text-blue-500 hover:bg-blue-500/5"
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 ring-4 ring-blue-500/10 animate-ping absolute" />
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 ring-2 ring-blue-500/15" />
            <span>编写中</span>
            <span className="font-bold font-sans px-1 rounded bg-blue-500/10 text-blue-400 text-[10px]">
              {chapters.filter(c => c.status === "writing").length}
            </span>
          </button>

          <button 
            onClick={() => setStatusFilter(statusFilter === "reviewing" ? "all" : "reviewing")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
              statusFilter === "reviewing" 
                ? "bg-amber-500/10 border-amber-500/30 text-amber-500" 
                : "border-transparent text-slate-500 hover:text-amber-500 hover:bg-amber-500/5"
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 ring-2 ring-amber-500/15" />
            <span>审核中</span>
            <span className="font-bold font-sans px-1 rounded bg-amber-500/10 text-amber-400 text-[10px]">
              {chapters.filter(c => c.status === "reviewing").length}
            </span>
          </button>

          <button 
            onClick={() => setStatusFilter(statusFilter === "completed" ? "all" : "completed")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
              statusFilter === "completed" 
                ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-555 dark:text-emerald-400" 
                : "border-transparent text-slate-500 hover:text-emerald-500 hover:bg-emerald-554/5"
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-emerald-500/15" />
            <span>已完成</span>
            <span className="font-bold font-sans px-1 rounded bg-emerald-500/10 text-emerald-400 text-[10px]">
              {completedChaptersCount} / {totalChaptersCount}
            </span>
          </button>
        </div>

        {/* Global prompt indicator */}
        <span className="hidden lg:inline-block text-[10px] text-slate-500 italic">
          &gt; FILTERS READY // CLICK STAT NODE TO PIN CATEGORIES
        </span>

      </div>

      {/* 4. WORKFLOW PROCESS SEQUENTIAL PHASES (流程进度) */}
      <div className="themed-card rounded-xl p-4 md:p-5 flex flex-col gap-3.5 border-[var(--border-color-muted)]">
        
        {/* Phase Header */}
        <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-2">
          <span className="text-[11px] font-cyber tracking-widest text-slate-500 uppercase">SYS STAGE PROGRESSION FLOW</span>
          <button 
            onClick={() => showToast("流程审计详情已发布：第一阶段AI拟编已于6月16日自动交付，当前人工二次解译覆盖中。")}
            className="text-xs text-blue-500 hover:text-blue-400 font-cyber flex items-center gap-0.5"
          >
            查看详情 <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* 4 Phase nodes */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 py-2 relative">
          
          {/* Timeline Node 1: Completed */}
          <div className="p-3 bg-emerald-500/5 border border-emerald-500/35 rounded-xl relative flex items-center gap-3">
            <div className="w-1.5 h-10 bg-emerald-500 rounded-full" />
            <div>
              <h4 className="text-xs font-bold text-[var(--text-main)]">1. AI编写初稿</h4>
              <p className="text-[10px] text-emerald-505 dark:text-emerald-450 font-cyber font-bold mt-0.5">COMPLETED // AI DRAFTED</p>
            </div>
            <div className="absolute right-3 top-3 w-4 h-4 bg-emerald-500/10 text-emerald-500 rounded-full flex items-center justify-center text-[9px] font-bold">✔</div>
          </div>

          {/* Timeline Node 2: Active / Current */}
          <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl relative flex items-center gap-3 shadow-[0_0_15px_rgba(37,99,235,0.15)] animate-pulse">
            <div className="w-1.5 h-10 bg-blue-500 rounded-full" />
            <div>
              <h4 className="text-xs font-bold text-[var(--text-main)] flex items-center gap-1.5">
                2. 人工修改确认
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping inline-block" />
              </h4>
              <p className="text-[10px] text-blue-500 font-cyber font-bold mt-0.5">ACTIVE WORK IN PROGRESS</p>
            </div>
          </div>

          {/* Timeline Node 3: Pending */}
          <div className="p-3 bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] rounded-xl relative flex items-center gap-3 opacity-60">
            <div className="w-1.5 h-10 bg-slate-500 rounded-full" />
            <div>
              <h4 className="text-xs font-bold text-[var(--text-main)]">3. 报告提交</h4>
              <p className="text-[10px] text-slate-500 font-cyber mt-0.5">PENDING SYNC PROTOCOLS</p>
            </div>
          </div>

          {/* Timeline Node 4: Pending */}
          <div className="p-3 bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] rounded-xl relative flex items-center gap-3 opacity-60">
            <div className="w-1.5 h-10 bg-slate-500 rounded-full" />
            <div>
              <h4 className="text-xs font-bold text-[var(--text-main)]">4. 报告审核</h4>
              <p className="text-[10px] text-slate-500 font-cyber mt-0.5">SCHEMATIC VERIFICATION</p>
            </div>
          </div>

        </div>

      </div>

      {/* 5. MAIN COLLABORATION GRID - LEFT WORKStage, RIGHT PROJECT TEAM */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        
        {/* LEFT STAGE: Tab view dependent (Overview Content Area / Editor / Review Workspace) */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          
          <AnimatePresence mode="wait">
            
            {/* SUB-VIEW 1: OVERVIEW COMPONENT (With lists vs Kanban Switcher) */}
            {activeSubTab === "overview" && (
              <motion.div
                key="subtab-overview"
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -15 }}
                className="flex flex-col gap-5"
              >
                
                {/* Outliner Switch Toolbar */}
                <div className="themed-card rounded-xl p-4 flex items-center justify-between border-[var(--border-color-muted)] bg-[var(--bg-secondary)]">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4.5 h-4.5 text-purple-500" />
                    <h3 className="text-sm font-bold text-[var(--text-main)] font-sans">
                      章节进度与结构规划
                    </h3>
                  </div>

                  {/* Mode Buttons */}
                  <div className="flex bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] rounded-lg p-0.5 relative">
                    <button
                      onClick={() => setLayoutMode("list")}
                      className={`px-3 py-1 rounded text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors ${
                        layoutMode === "list" 
                          ? "bg-slate-500/15 text-purple-505 dark:text-purple-400 border border-purple-500/20" 
                          : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
                      }`}
                    >
                      <ListFilter className="w-3.5 h-3.5" />
                      <span>列表模式</span>
                    </button>
                    <button
                      onClick={() => setLayoutMode("kanban")}
                      className={`px-3 py-1 rounded text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors ${
                        layoutMode === "kanban" 
                          ? "bg-slate-500/15 text-purple-555 dark:text-purple-400 border border-purple-500/20" 
                          : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
                      }`}
                    >
                      <LayoutGrid className="w-3.5 h-3.5" />
                      <span>看板模式</span>
                    </button>
                  </div>
                </div>

                {/* VIEW CONFIG 1: LIST 대纲 TREE OUTLINER */}
                {layoutMode === "list" ? (
                  <div className="themed-card rounded-xl p-4 md:p-5 flex flex-col gap-3 min-h-[300px] border-[var(--border-color-muted)] overflow-hidden">
                    
                    {/* Header line */}
                    <div className="flex items-center justify-between text-[11px] font-cyber text-slate-500 border-b border-[var(--border-color-muted)] pb-2 mb-1.5">
                      <span>PROJECT OUTLINE NODE TREE</span>
                      <span>TOTAL LISTINGS: {filteredChapters.length}</span>
                    </div>

                    <div className="flex flex-col gap-2 max-h-[480px] overflow-y-auto pr-1">
                      {filteredChapters.map(chap => {
                        const isSubHeader = chap.parentId !== undefined;
                        
                        return (
                          <div
                            key={chap.id}
                            style={{ paddingLeft: isSubHeader ? "2.5rem" : "0.5rem" }}
                            className={`p-3 rounded-lg border transition-all flex flex-col md:flex-row md:items-center justify-between gap-3 group relative cursor-pointer ${
                              selectedChapterId === chap.id 
                                ? "bg-purple-500/10 border-purple-500/50 glow-purple" 
                                : isSubHeader 
                                ? "bg-slate-400/5 hover:bg-slate-400/10 border-transparent hover:border-[var(--border-color)]" 
                                : "bg-slate-400/5 hover:bg-slate-400/15 border-[var(--border-color-muted)] hover:border-purple-500/20"
                            }`}
                            onClick={() => {
                              setSelectedChapterId(chap.id);
                              setActiveSubTab("editor"); // direct transition to editor workbench when clicked inside!
                              showToast(`已装载并渲染章节 [${chap.sectionNumber} ${chap.title}] 到编辑工作台。`);
                            }}
                          >
                            <div className="flex items-start gap-2.5 min-w-0">
                              <span className="text-[10px] font-cyber bg-slate-500/10 text-slate-500 font-bold px-1.5 py-0.5 rounded-md mt-0.5">
                                {chap.sectionNumber}
                              </span>
                              <div className="min-w-0">
                                <h4 className={`text-xs font-bold truncate group-hover:text-purple-650 dark:group-hover:text-purple-400 transition-colors font-sans ${
                                  isSubHeader ? "text-[var(--text-main)] font-medium" : "text-[var(--text-main)] text-sm"
                                }`}>
                                  {chap.title}
                                </h4>
                                <p className="text-[10px] text-slate-500 truncate max-w-[450px] font-sans font-normal mt-0.5 leading-normal">
                                  {chap.content}
                                </p>
                              </div>
                            </div>

                            {/* Tags and assignees on right side */}
                            <div className="flex items-center gap-3.5 flex-shrink-0 self-end md:self-center">
                              <span className="text-[10px] font-cyber text-slate-500 lowercase">
                                {chap.timeAgo}
                              </span>
                              
                              <span className="text-[10px] font-sans px-2 py-0.5 rounded bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] text-[var(--text-muted)] font-semibold">
                                {chap.assignee}
                              </span>

                              {/* Completed Badge */}
                              <span className={`text-[10px] font-sans px-2 py-0.5 rounded font-bold ${
                                chap.status === "completed" ? "bg-emerald-500/10 text-emerald-555 dark:text-emerald-400 border border-emerald-500/20" :
                                chap.status === "reviewing" ? "bg-amber-500/10 text-amber-555 dark:text-amber-400" :
                                "bg-slate-400/15 text-slate-400"
                              }`}>
                                {chap.status === "completed" ? `已完成 ${chap.progress}%` :
                                 chap.status === "reviewing" ? "审核中" : "正在编写"}
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  
                  // VIEW CONFIG 2: DYNAMIC METED STAT KANBAN BOARD SYSTEM
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-start min-h-[380px]">
                    
                    {/* Column 1: Pending */}
                    <div className="themed-card rounded-xl p-3 flex flex-col gap-3 min-h-[350px] border-[var(--border-color-muted)]">
                      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-2 mb-1">
                        <span className="text-xs font-bold text-[var(--text-main)] font-sans">待编写</span>
                        <span className="font-cyber font-bold text-[10px] bg-slate-500/10 px-1.5 py-0.5 rounded text-slate-500">
                          {chapters.filter(c => c.status === "pending").length}
                        </span>
                      </div>
                      
                      {chapters.filter(c => c.status === "pending").map(chap => renderKanbanCard(chap))}
                      {chapters.filter(c => c.status === "pending").length === 0 && (
                        <div className="text-[10px] text-center font-cyber text-slate-500 italic py-10">
                          &gt; COLUMN EMPTY
                        </div>
                      )}
                    </div>

                    {/* Column 2: Writing */}
                    <div className="themed-card rounded-xl p-3 flex flex-col gap-3 min-h-[350px] border-[var(--border-color-muted)]">
                      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-2 mb-1">
                        <span className="text-xs font-bold text-[var(--text-main)] font-sans">编写中</span>
                        <span className="font-cyber font-bold text-[10px] bg-blue-500/10 px-1.5 py-0.5 rounded text-blue-500">
                          {chapters.filter(c => c.status === "writing").length}
                        </span>
                      </div>
                      
                      {chapters.filter(c => c.status === "writing").map(chap => renderKanbanCard(chap))}
                      {chapters.filter(c => c.status === "writing").length === 0 && (
                        <div className="text-[10px] text-center font-cyber text-slate-500 italic py-10">
                          &gt; COLUMN EMPTY
                        </div>
                      )}
                    </div>

                    {/* Column 3: Reviewing */}
                    <div className="themed-card rounded-xl p-3 flex flex-col gap-3 min-h-[350px] border-[var(--border-color-muted)]">
                      <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-2 mb-1">
                        <span className="text-xs font-bold text-[var(--text-main)] font-sans">审核中</span>
                        <span className="font-cyber font-bold text-[10px] bg-amber-500/10 px-1.5 py-0.5 rounded text-amber-500 font-bold">
                          {chapters.filter(c => c.status === "reviewing").length}
                        </span>
                      </div>
                      
                      {chapters.filter(c => c.status === "reviewing").map(chap => renderKanbanCard(chap))}
                      {chapters.filter(c => c.status === "reviewing").length === 0 && (
                        <div className="text-[10px] text-center font-cyber text-slate-500 italic py-10">
                          &gt; COLUMN EMPTY
                        </div>
                      )}
                    </div>

                    {/* Column 4: Completed - Preseeded with prototype data */}
                    <div className="themed-card rounded-xl p-3 flex flex-col gap-3 min-h-[350px] border-emerald-500/10 bg-emerald-500/5">
                      <div className="flex items-center justify-between border-b border-emerald-500/15 pb-2 mb-1">
                        <span className="text-xs font-bold text-[var(--text-main)] font-sans">已完成</span>
                        <span className="font-cyber font-bold text-[10px] bg-emerald-500/10 px-1.5 py-0.5 rounded text-emerald-400 font-bold">
                          {completedChaptersCount}
                        </span>
                      </div>
                      
                      {/* Render completed entries in Kanban format */}
                      <div className="flex flex-col gap-2 max-h-[420px] overflow-y-auto pr-1">
                        {chapters.filter(c => c.status === "completed").map(chap => renderKanbanCard(chap))}
                      </div>
                    </div>

                  </div>

                )}

              </motion.div>
            )}

            {/* SUB-VIEW 2: ADVANCED DOCUMENT EDITOR (文档编辑 - CO-WRITER WORKStage) */}
            {activeSubTab === "editor" && (
              <motion.div
                key="subtab-editor"
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -15 }}
                className="grid grid-cols-1 md:grid-cols-12 gap-5"
              >
                
                {/* Left Chapter mini bar - 4 cols */}
                <div className="md:col-span-4 flex flex-col gap-3 themed-card rounded-xl p-3 md:p-4 max-h-[500px] overflow-y-auto border-[var(--border-color-muted)]">
                  <div className="text-xs font-bold pb-2 border-b border-[var(--border-color-muted)] text-slate-500 uppercase tracking-wider font-cyber">
                    大纲树选编 / Document Outline
                  </div>
                  {chapters.map(chap => (
                    <button
                      key={chap.id}
                      onClick={() => setSelectedChapterId(chap.id)}
                      className={`p-2.5 rounded-lg text-left text-xs transition-all flex items-center justify-between gap-1.5 cursor-pointer ${
                        selectedChapterId === chap.id 
                          ? "bg-purple-600 text-white font-bold" 
                          : "bg-slate-400/5 hover:bg-slate-400/10 text-[var(--text-muted)] hover:text-[var(--text-main)]"
                      }`}
                    >
                      <div className="truncate min-w-0">
                        <span className="font-cyber font-bold opacity-80 mr-1.5">{chap.sectionNumber}</span>
                        <span>{chap.title}</span>
                      </div>
                      
                      {chap.status === "completed" && (
                        <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                      )}
                    </button>
                  ))}
                </div>

                {/* Center / Right Core Draft Canvas - 8 cols */}
                <div className="md:col-span-8 flex flex-col gap-4 themed-card rounded-xl p-4 md:p-5 border-[var(--border-color-muted)]">
                  
                  {/* Title of node */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-[var(--border-color-muted)] pb-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-cyber bg-purple-500/10 border border-purple-500/20 text-purple-400 px-2 py-0.5 rounded font-bold">
                          SEC: {activeChapter.sectionNumber}
                        </span>
                        <span className="text-[10px] font-sans px-2 py-0.5 rounded bg-slate-400/10 text-slate-500">
                          编撰者: {activeChapter.assignee}
                        </span>
                      </div>
                      <h3 className="text-sm font-bold text-[var(--text-main)] font-sans mt-1.5 truncate">
                        {activeChapter.title}
                      </h3>
                    </div>

                    {/* AI Quick buttons bar */}
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => handleAiAssistMode("expand")}
                        disabled={isSaving}
                        className="px-2.5 py-1.5 rounded bg-blue-600/10 border border-blue-500/20 text-blue-600 dark:text-blue-400 hover:bg-blue-600/20 text-[10px] font-bold transition-all flex items-center gap-1 cursor-pointer"
                        title="AI自动撰写与扩写段落"
                      >
                        <Sparkles className="w-3 h-3 animate-pulse text-blue-500" />
                        <span>💡 AI扩写</span>
                      </button>

                      <button
                        onClick={() => handleAiAssistMode("polish")}
                        disabled={isSaving}
                        className="px-2.5 py-1.5 rounded bg-purple-600/10 border border-purple-500/20 text-purple-600 dark:text-purple-400 hover:bg-purple-600/20 text-[10px] font-bold transition-all flex items-center gap-1 cursor-pointer"
                        title="修润规范专有技术词汇语风"
                      >
                        <Edit3 className="w-3 h-3 text-purple-500" />
                        <span>⚡ 润色</span>
                      </button>

                      <button
                        onClick={() => handleAiAssistMode("audit")}
                        disabled={isSaving}
                        className="px-2.5 py-1.5 rounded bg-red-605/10 border border-red-500/20 text-red-500 hover:bg-red-500/20 text-[10px] font-bold transition-all flex items-center gap-1 cursor-pointer"
                        title="自检本段安全与化工防灾红线遗漏"
                      >
                        <ShieldAlert className="w-3 h-3 animate-bounce" />
                        <span>🛡 合规自检</span>
                      </button>
                    </div>
                  </div>

                  {/* Editor Canvas Block */}
                  <div className="flex-1 flex flex-col gap-2 min-h-[250px]">
                    <label className="text-[10px] font-cyber text-slate-500 select-none">QUANTUM TEXT WRITING BUFFER WORKSPACE // EDIT DIRECTLY</label>
                    <textarea
                      value={activeChapterContent}
                      onChange={e => setActiveChapterContent(e.target.value)}
                      disabled={isSaving}
                      placeholder="编辑该章节的化工防灾大纲详细规范配置..."
                      className="w-full flex-1 bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] text-[var(--text-main)] rounded-lg p-3 text-xs leading-relaxed outline-none focus:border-purple-500/40 font-mono resize-none h-[220px]"
                    />
                  </div>

                  {/* Submission and History */}
                  <div className="flex items-center justify-between mt-1 pt-3 border-t border-[var(--border-color-muted)] text-xs">
                    <span className="text-[10px] font-cyber text-slate-500">
                      SYS AUTOSAVED DEPLOYMENTS // REV: {revisionHistory.filter(h => h.rev.includes(activeChapter.sectionNumber)).length + 1}
                    </span>
                    
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleSaveActiveChapter}
                        disabled={isSaving}
                        className="px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:opacity-90 active:scale-95 text-white font-bold rounded-lg flex items-center gap-1.5 transition-all cursor-pointer text-xs"
                      >
                        {isSaving ? (
                          <RotateCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Save className="w-3.5 h-3.5" />
                        )}
                        <span>存盘部署 (Save Revision)</span>
                      </button>
                    </div>
                  </div>

                </div>

              </motion.div>
            )}

            {/* SUB-VIEW 3: REVIEW WORKBENCH (审核工作台) */}
            {activeSubTab === "review" && (
              <motion.div
                key="subtab-review"
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -15 }}
                className="themed-card rounded-xl p-4 md:p-6 flex flex-col gap-5 border-[var(--border-color-muted)] min-h-[300px]"
              >
                
                {/* Header */}
                <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-teal-500" />
                    <h3 className="text-sm font-bold text-[var(--text-main)] font-sans uppercase">
                      辽阳石化 - 技术审查核心控制台 / Review Console
                    </h3>
                  </div>
                  <span className="text-[10px] font-cyber bg-teal-500/10 border border-teal-500/20 text-teal-400 px-2 py-0.5 rounded font-bold">
                    SECURITY ACCESS LEVEL A
                  </span>
                </div>

                {/* Audit Items */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  
                  {/* Left checklist */}
                  <div className="themed-terminal p-4 rounded-xl flex flex-col gap-3">
                    <span className="text-[10px] font-cyber text-slate-500 uppercase tracking-widest block mb-1">AUTOMATION FIRE COMPLIANCE CHECKLIST</span>
                    
                    <div className="flex items-center gap-2 text-xs py-1 border-b border-[var(--border-color-muted)]">
                      <CheckSquare className="w-4 h-4 text-emerald-450 text-emerald-500" />
                      <span className="text-slate-450 dark:text-slate-350">《常减压加氢防火自检间距》核对1.5km</span>
                    </div>

                    <div className="flex items-center gap-2 text-xs py-1 border-b border-[var(--border-color-muted)]">
                      <CheckSquare className="w-4 h-4 text-emerald-450 text-emerald-500" />
                      <span className="text-slate-450 dark:text-slate-350">《消防自喷淋多重联配泡沫发生器》压力核定</span>
                    </div>

                    <div className="flex items-center gap-2 text-xs py-1 border-b border-[var(--border-color-muted)]">
                      <CheckSquare className="w-4 h-4 text-emerald-450 text-emerald-500" />
                      <span className="text-slate-450 dark:text-slate-350">《危化罐防火二级沙堰容积》3.5万立方验证</span>
                    </div>

                    <div className="flex items-center gap-2 text-xs py-1">
                      <CheckSquare className="w-4 h-4 text-slate-500 animate-pulse" />
                      <span className="text-[var(--text-main)] font-bold">《可燃浓度光谱探头秒级自动自锁联动》</span>
                    </div>
                  </div>

                  {/* Right sign-off block */}
                  <div className="themed-terminal p-4 rounded-xl flex flex-col justify-between h-full bg-teal-500/5 border-teal-500/15">
                    <div>
                      <span className="text-[10px] font-cyber text-teal-500 uppercase tracking-widest block mb-2">CRYPTOGRAPHIC WORKBENCH APPROVED SIGN-OFF</span>
                      <p className="text-xs text-[var(--text-muted)] leading-relaxed font-sans mb-3 font-normal">
                        当所有章节完全经由负责人 (lisi / E2E Lead) 人工重写、AI自检校验无误后，即可执行多维防灾审计签准，并在控制台生成区块链安全证书防伪码进行正式出图分发。
                      </p>
                    </div>

                    <button
                      onClick={() => showToast("🔒 已签准！正在对该项目报告加密并交付辽阳省特种行业消防审验机构，出图证书编号: SYS_CERT_2026_7793.")}
                      className="w-full py-2.5 bg-gradient-to-r from-teal-600 to-emerald-600 text-white font-bold text-xs rounded-lg shadow-lg hover:shadow-teal-500/20 hover:opacity-90 cursor-pointer flex items-center justify-center gap-1.5"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      <span>通过审核并加密出图 (Establish Secure Release)</span>
                     </button>
                  </div>

                </div>

                {/* Audit trail */}
                <div className="p-3 bg-[var(--bg-tertiary)] rounded-xl border border-[var(--border-color-muted)] font-mono text-[10px] text-slate-500">
                  <div className="text-slate-505 dark:text-slate-400 font-bold mb-1">&gt; AUDIT TRACE LOG ENGINE:</div>
                  <div className="flex items-center gap-3">
                    <span>[2026-06-20 09:22] - zhaoliu 完成了章节 1.3 的编写修改。</span>
                    <span>•</span>
                    <span>[2026-06-22 03:14] - AI自动完成了希尔德安全自检。</span>
                  </div>
                </div>

              </motion.div>
            )}

          </AnimatePresence>

          {/* SHARED COMPONENT BOTTOM: Revision Log Node List */}
          <div className="themed-card rounded-xl p-4 md:p-5 flex flex-col gap-3 border-[var(--border-color-muted)] bg-[var(--bg-secondary)] text-xs duration-300">
            <div className="text-xs font-bold font-sans text-[var(--text-main)] border-b border-[var(--border-color-muted)] pb-2 mb-1 flex items-center gap-1.5">
              <Terminal className="w-4 h-4 text-purple-500 animate-pulse" />
              <span>版本更迭记录 // System Revision Ledger</span>
            </div>
            <div className="flex flex-col gap-2 max-h-[140px] overflow-y-auto">
              {revisionHistory.map((hist, ind) => (
                <div key={hist.id} className="grid grid-cols-12 gap-2 text-[11px] font-mono border-b border-[var(--border-color-muted)] pb-1.5 items-center">
                  <span className="col-span-2 text-slate-500 font-cyber">#{ind+1} NODE</span>
                  <span className="col-span-3 text-cyan-555 dark:text-cyan-400 font-bold">{hist.user}</span>
                  <span className="col-span-5 text-slate-455 dark:text-slate-400 truncate">{hist.rev}</span>
                  <span className="col-span-2 text-right text-slate-500">{hist.time}</span>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* RIGHT SIDEBAR: Members, Files & Knowledge repository */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          
          {/* Members list (项目成员 Block) */}
          <div className="themed-card rounded-xl p-4 md:p-5 relative flex flex-col border-[var(--border-color-muted)]">
            <div className="absolute top-0 right-0 w-2 h-2 bg-purple-500/10" />
            
            {/* Header */}
            <div className="flex items-center justify-between border-b border-[var(--border-color-muted)] pb-3 mb-4">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-purple-500" />
                <h3 className="text-sm font-bold text-[var(--text-main)] uppercase tracking-wider font-sans">
                  项目成员 <span className="text-[10px] font-normal text-slate-500 font-cyber">Project Members</span>
                </h3>
              </div>
              <button
                onClick={() => setShowAddMember(!showAddMember)}
                className="text-xs text-purple-555 hover:text-purple-650 cursor-pointer flex items-center gap-0.5 font-bold font-sans"
              >
                {showAddMember ? "✖ 折叠" : "✚ 添加成员"}
              </button>
            </div>

            {/* Add Member inline form */}
            <AnimatePresence>
              {showAddMember && (
                <motion.form
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  onSubmit={handleAddMemberSubmit}
                  className="mb-4 p-3 border border-purple-500/20 bg-purple-500/5 rounded-lg text-xs flex flex-col gap-2.5 overflow-hidden font-sans"
                >
                  <div>
                    <label className="block text-[var(--text-muted)] mb-1">成员拼音标识码 (ID)</label>
                    <input
                      type="text"
                      required
                      placeholder="例如: sunqi / lisi"
                      value={newMemberName}
                      onChange={e => setNewMemberName(e.target.value)}
                      className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] text-[var(--text-main)] rounded px-2 py-1 outline-none focus:border-purple-500/40"
                    />
                  </div>
                  <div>
                    <label className="block text-[var(--text-muted)] mb-1">职能定位</label>
                    <select
                      value={newMemberRole}
                      onChange={e => setNewMemberRole(e.target.value as "负责人" | "成员")}
                      className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] text-[var(--text-main)] rounded px-2 py-1 outline-none cursor-pointer"
                    >
                      <option value="成员">普通成员 (Researcher)</option>
                      <option value="负责人">项目负责人 (E2E Lead)</option>
                    </select>
                  </div>
                  <button
                    type="submit"
                    className="w-full py-1.5 bg-purple-600 hover:bg-purple-500 border border-purple-400/20 text-white font-bold rounded cursor-pointer"
                  >
                    批准加入班组
                  </button>
                </motion.form>
              )}
            </AnimatePresence>

            {/* List members */}
            <div className="flex flex-col gap-3">
              {members.map(member => (
                <div
                  key={member.id}
                  className="flex items-center justify-between p-3 rounded-lg border border-[var(--border-color-muted)] bg-slate-400/5 hover:bg-slate-400/10 group transition-all"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-xs capitalize ${member.avatarColor}`}>
                      {member.name.substring(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-[var(--text-main)]">{member.name}</h4>
                      <p className="text-[10px] text-slate-500 font-mono">NODE ACTIVE USER // ID: {member.id}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className={`text-[9px] px-1.5 py-0.5 rounded font-cyber font-bold select-none ${
                      member.role === "负责人" 
                        ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20" 
                        : "bg-slate-400/15 text-[var(--text-muted)] border border-transparent"
                    }`}>
                      {member.role}
                    </span>

                    {/* Trash can delete button */}
                    <button
                      onClick={() => handleDeleteMember(member.id, member.name)}
                      className="p-1 text-slate-550 hover:text-red-500 hover:bg-red-500/5 rounded transition-all cursor-pointer opacity-0 group-hover:opacity-100"
                      title="撤销该成员"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

          </div>

          {/* Live AI Chapter Advice generator */}
          <div className="themed-card rounded-xl p-4 md:p-5 flex flex-col border-[var(--border-color-muted)] relative overflow-hidden bg-gradient-to-br from-blue-500/5 to-purple-500/5">
            <div className="absolute top-0 right-0 w-2 h-2 bg-blue-500/10" />
            <div className="flex items-center gap-2 border-b border-[var(--border-color-muted)] pb-3 mb-3">
              <div className="p-1 rounded bg-blue-500/15 text-blue-500">
                <Cpu className="w-4 h-4 animate-spin-slow" />
              </div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-main)] font-cyber">
                防灾解译神经网络 / Prometheus Heuristics
              </h3>
            </div>
            
            <p className="text-[11px] text-[var(--text-muted)] leading-relaxed font-sans font-normal">
              当前工艺段高危险参数：新建加氢反应段工艺压力高达<strong>15.2MPa</strong>，温度<strong>390℃</strong>。建议全章编制引入多级氮气阻断、安全泄放回路校验与远程激光吸收可燃探头，保证E2E编制报告最终通检。
            </p>
          </div>

        </div>

      </div>

      {/* 6. AI CO-WRITER CHAT PANEL (进入对话 SLIDE OUT) */}
      <AnimatePresence>
        {aiChatOpen && (
          <div className="fixed inset-y-0 right-0 z-50 w-full sm:w-[450px] bg-[var(--bg-secondary)] border-l border-[var(--border-color)] shadow-2xl flex flex-col backdrop-blur-xl duration-300">
            {/* Absolute header bar */}
            <div className="flex items-center justify-between p-4 border-b border-[var(--border-color-muted)] bg-[var(--bg-tertiary)]">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-blue-500/10 border border-blue-500/20 text-blue-500 rounded-md">
                  <Sparkles className="w-4 h-4 animate-spin-slow" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[var(--text-main)] font-sans">希尔德防灾AI写作助手</h3>
                  <p className="text-[9px] text-slate-500 font-cyber">MODEL: STARDOCK-PRO-FLASH</p>
                </div>
              </div>
              <button 
                onClick={() => setAiChatOpen(false)}
                className="p-1 rounded hover:bg-slate-400/10 text-slate-500 hover:text-[var(--text-main)] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Message Logs */}
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
              {aiMessages.map((msg, i) => (
                <div 
                  key={i} 
                  className={`flex flex-col max-w-[85%] ${msg.sender === "user" ? "self-end items-end" : "self-start items-start"}`}
                >
                  <div className={`p-3 rounded-xl text-xs gap-1.5 flex flex-col ${
                    msg.sender === "user" 
                      ? "bg-blue-600 text-white rounded-tr-none shadow-md"
                      : "bg-[var(--bg-tertiary)] border border-[var(--border-color-muted)] text-[var(--text-main)] rounded-tl-none font-mono"
                  }`}>
                    {msg.sender === "ai" && (
                      <span className="text-[8px] font-cyber tracking-widest text-[#06b6d4] font-bold block border-b border-cyan-500/10 pb-1 mb-1">
                        &gt; NEURAL RESPONSE LOG
                      </span>
                    )}
                    <span className="whitespace-pre-wrap leading-relaxed">{msg.text}</span>
                  </div>
                  <span className="text-[9px] font-cyber text-slate-550 dark:text-slate-500 mt-1">{msg.time}</span>
                </div>
              ))}
              
              {/* Message Typing loader block */}
              {aiChatLoading && (
                <div className="self-start flex flex-col items-start gap-1 max-w-[85%]">
                  <div className="p-3.5 bg-[var(--bg-tertiary)] border border-cyan-500/20 text-[var(--text-main)] rounded-xl rounded-tl-none flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-[#06b6d4] animate-bounce" />
                    <div className="w-1.5 h-1.5 rounded-full bg-[#06b6d4] animate-bounce [animation-delay:0.2s]" />
                    <div className="w-1.5 h-1.5 rounded-full bg-[#06b6d4] animate-bounce [animation-delay:0.4s]" />
                  </div>
                </div>
              )}
            </div>

            {/* Input Bar */}
            <form onSubmit={handleSendMessage} className="p-4 border-t border-[var(--border-color-muted)] bg-[var(--bg-tertiary)] flex gap-2">
              <input
                type="text"
                value={aiInput}
                onChange={e => setAiInput(e.target.value)}
                placeholder="发送提问：'写一段关于消火栓规范描述'..."
                className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border-color-muted)] text-[var(--text-main)] rounded-lg px-3 py-2 text-xs outline-none focus:border-blue-500/30"
              />
              <button
                type="submit"
                disabled={!aiInput.trim() || aiChatLoading}
                className="px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg flex items-center justify-center transition-all cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>

          </div>
        )}
      </AnimatePresence>

    </div>
  );

  // Kanban Card Renderer
  function renderKanbanCard(chap: Chapter) {
    const isCompleted = chap.status === "completed";
    return (
      <motion.div
        layout
        whileHover={{ scale: 1.02 }}
        key={chap.id}
        onClick={() => {
          setSelectedChapterId(chap.id);
          setActiveSubTab("editor");
          showToast(`已装载并渲染章节 [${chap.sectionNumber} ${chap.title}] 到编辑工作台。`);
        }}
        className={`p-3 border rounded-xl flex flex-col justify-between cursor-pointer transition-all ${
          selectedChapterId === chap.id 
            ? "bg-purple-500/10 border-purple-500/40 glow-purple" 
            : "bg-[var(--bg-tertiary)] border-[var(--border-color-muted)] hover:border-purple-500/30"
        }`}
      >
        <div className="flex items-start justify-between gap-1 mb-1.5">
          <span className="text-[9px] font-cyber px-1.5 py-0.5 rounded bg-slate-500/10 text-slate-500 font-bold block">
            {chap.sectionNumber}
          </span>
          <span className="text-[9px] text-slate-500 font-sans font-medium">{chap.assignee}</span>
        </div>

        <h4 className="text-xs font-bold text-[var(--text-main)] line-clamp-1 mb-2 font-sans text-left">
          {chap.title}
        </h4>

        {/* Dynamic Progress indicator representation matching screenshot card style */}
        <div className="flex flex-col gap-1 mt-1 font-cyber text-[8px] text-slate-550 dark:text-slate-500 text-left">
          <div className="flex items-center justify-between font-mono">
            <span>Progress:</span>
            <span className={isCompleted ? "text-emerald-500 font-bold" : "text-purple-400 font-bold"}>{chap.progress}%</span>
          </div>
          <div className="w-full h-1 bg-slate-100 dark:bg-slate-850 rounded-full overflow-hidden relative">
            <div 
              className={`h-full rounded-full transition-all duration-500 ${isCompleted ? "bg-emerald-500" : "bg-purple-500"}`} 
              style={{ width: `${Math.min(chap.progress, 100)}%` }}
            />
          </div>
        </div>
      </motion.div>
    );
  }
}
