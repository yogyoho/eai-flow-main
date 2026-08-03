"use client";

import { motion, type Variants } from "framer-motion";
import {
  Rocket,
  FolderCog,
  Star,
  CheckCircle2,
  GitMerge,
  ShieldCheck,
  BarChart2,
  BookOpen,
  Network,
  FileText,
  Layers,
  UserCircle,
  ArrowRight,
  Sparkles,
  LogIn,
  LogOutIcon,
  Factory,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import React, { useCallback, useState } from "react";

import "./index.css";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MobileNav } from "@/components/landing/mobile-nav";
import { useAuth } from "@/extensions/hooks/useAuth";

export default function LandingNew() {
  const [mounted, setMounted] = useState(false);
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const handleNavClick = useCallback((path: string) => {
    if (!user) {
      const redirect = encodeURIComponent(path);
      router.push(`/login?redirect=${redirect}`);
    } else {
      router.push(path);
    }
  }, [user, router]);

  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants: Variants = {
    hidden: { y: 20, opacity: 0 },
    visible: {
      y: 0,
      opacity: 1,
      transition: { type: "spring" as const, stiffness: 100, damping: 15 },
    },
  };

  return (
    <div className="min-h-screen relative bg-background dark:bg-[#0a0a0a] overflow-hidden font-sans"> 
      {/* 科技感背景：网格与柔和光晕 */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 bg-grid-pattern opacity-60"></div>
        {/* 左下角蓝色光晕 */}
        <div className="absolute -left-[20%] top-[40%] w-[60%] h-[60%] rounded-full bg-primary/10 blur-[120px]"></div>
        {/* 右上角青色光晕 */}
        <div className="absolute -right-[10%] -top-[10%] w-[50%] h-[50%] rounded-full bg-teal-400/10 blur-[120px]"></div>
      </div>

      {/* 顶部导航栏 */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-4 bg-card/70 dark:bg-card/70 backdrop-blur-md border-b border-border dark:border-border">
        <div className="flex items-center space-x-3">
          {/* Logo */}
          <img
            src="/favicon.svg"
            alt="Logo"
            className="w-8 h-auto object-contain"
          />
          <span className="text-xl font-bold text-primary tracking-wide">
            吉林化工工程有限公司
          </span>
        </div>

        <div className="hidden md:flex items-center space-x-2 text-muted-foreground dark:text-muted-foreground font-medium">
          <button onClick={() => handleNavClick("/workspace/chats/new")} className="px-4 py-2 rounded-lg hover:bg-primary/10 hover:text-primary transition-all duration-200">工程报告</button>
          <button onClick={() => handleNavClick("/knowledge-factory?tab=reports")} className="px-4 py-2 rounded-lg hover:bg-primary/10 hover:text-primary transition-all duration-200">知识工厂</button>
          <button onClick={() => handleNavClick("/docmgr")} className="px-4 py-2 rounded-lg hover:bg-primary/10 hover:text-primary transition-all duration-200">文档空间</button>
          <button onClick={() => handleNavClick("/settings")} className="px-4 py-2 rounded-lg hover:bg-primary/10 hover:text-primary transition-all duration-200">设置</button>
        </div>
        <MobileNav links={[
          { href: "/workspace/chats/new", label: "工程报告" },
          { href: "/knowledge-factory?tab=reports", label: "知识工厂" },
          { href: "/docmgr", label: "文档空间" },
          { href: "/settings", label: "设置" },
        ]} />

        <div className="flex items-center">
          {!isLoading && (
            user ? (
              mounted ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground text-sm whitespace-nowrap">
                      <UserCircle className="w-6 h-6" strokeWidth={1.5} />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent className="w-64 rounded-xl" align="end" sideOffset={8}>
                    <div className="px-3 py-2 border-b border-border dark:border-border">
                      <p className="text-sm font-medium text-foreground dark:text-foreground">{user.username}</p>
                      <p className="text-xs text-muted-foreground dark:text-muted-foreground">{user.email}</p>
                    </div>
                    <DropdownMenuGroup className="py-1">
                      <DropdownMenuItem onClick={() => router.push("/knowledge")}>
                        <BookOpen className="mr-2 h-4 w-4" />
                        知识库
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => router.push("/knowledge-factory")}>
                        <Factory className="mr-2 h-4 w-4" />
                        知识工厂
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => router.push("/procurement")}>
                        <Network className="mr-2 h-4 w-4" />
                        采购管理
                      </DropdownMenuItem>
                    </DropdownMenuGroup>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={logout} className="text-red-500 dark:text-red-400 focus:text-red-500 dark:focus:text-red-400">
                      <LogOutIcon className="mr-2 h-4 w-4" />
                      退出登录
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <div className="w-9 h-9 rounded-full bg-primary/10 animate-pulse" />
              )
            ) : (
              <button
                onClick={() => router.push("/login")}
                className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground text-sm whitespace-nowrap"
              >
                <LogIn className="w-4 h-4" />
                登录
              </button>
            )
          )}
        </div>
      </nav>

      {/* 主内容区 */}
      <main className="relative z-10 max-w-7xl mx-auto px-6 pt-20 pb-24">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center"
        >
          {/* 左侧：Hero 文本区 */}
          <div className="space-y-8">
            <motion.div variants={itemVariants}>
              <span className="inline-flex items-center space-x-2 px-4 py-1.5 rounded-full bg-primary/10 text-primary text-sm font-medium border border-primary/20">
                <Sparkles className="w-4 h-4" />
                <span>企业智能体平台套件，融合知识工厂与RAG知识库</span>
              </span>
            </motion.div>

            <motion.div variants={itemVariants} className="space-y-6">
              <h1 className="text-3xl md:text-6xl font-extrabold text-foreground dark:text-white leading-[1.15] tracking-tight">
                吉林化工工程: 石化设计领域智能应用平台
              </h1>
              {/* 渐变装饰线 */}
              <div className="h-1.5 w-full bg-gradient-to-r from-primary via-primary/70 to-teal-400 rounded-full"></div>
              <p className="text-xl text-muted-foreground dark:text-muted-foreground font-medium">
                统一编排 Agent、知识库、skills、MCP与工具链
              </p>
            </motion.div>

            <motion.div variants={itemVariants} className="flex flex-wrap gap-4 pt-4">
              <button
                onClick={() => handleNavClick("/workspace/chats/new")}
                className="flex items-center space-x-2 px-8 py-3.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl font-medium shadow-lg shadow-primary/20 transition-colors"
              >
                <Rocket className="w-5 h-5" />
                <span>开始写作</span>
              </button>
              <button
                onClick={() => handleNavClick("/knowledge-factory?tab=reports")}
                className="flex items-center space-x-2 px-8 py-3.5 bg-card dark:bg-card hover:bg-primary/10 text-primary border border-primary/30 hover:border-primary/50 rounded-xl font-medium shadow-sm transition-all duration-200 hover:shadow-md hover:shadow-primary/15 hover:scale-[1.02] hover:-translate-y-0.5 active:scale-[0.98]"
              >
                <FolderCog className="w-5 h-5" />
                <span>知识加工</span>
              </button>
            </motion.div>
          </div>

          {/* 右侧：数据统计卡片 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 relative">
            {/* 装饰性背景 — subtle warm glow in light, cool glow in dark */}
            <div className="absolute -inset-10 bg-primary/5 dark:bg-primary/[0.03] blur-[100px] rounded-full -z-10" />
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[60%] bg-teal-400/5 dark:bg-teal-400/[0.04] blur-[80px] rounded-full -z-10" />

            <StatsCard
              variants={itemVariants}
              icon={<Star className="w-5 h-5" />}
              number="2300+"
              title="知识量"
              desc="业务人员的参与与支持"
              accent="amber"
            />
            <StatsCard
              variants={itemVariants}
              icon={<CheckCircle2 className="w-5 h-5" />}
              number="200+"
              title="SKILLS数量"
              desc="持续改进和问题解决能力"
              accent="emerald"
            />
            <StatsCard
              variants={itemVariants}
              icon={<GitMerge className="w-5 h-5" />}
              number="50+"
              title="MCP数量"
              desc="活跃的开发迭代和功能更新"
              accent="violet"
            />
            <StatsCard
              variants={itemVariants}
              icon={<ShieldCheck className="w-5 h-5" />}
              number="10+"
              title="报告种类"
              desc="煤炭行业工程设计类报告生成"
              accent="sky"
            />
          </div>
        </motion.div>

        {/* 快速访问区域 */}
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          variants={containerVariants}
          className="mt-32"
        >
          <div className="text-center mb-12 space-y-3">
            <motion.h2 variants={itemVariants} className="text-3xl font-bold text-foreground dark:text-white">
              快速访问
            </motion.h2>
            <motion.p variants={itemVariants} className="text-muted-foreground dark:text-muted-foreground">
              探索平台核心功能模块
            </motion.p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <QuickAccessCard
              variants={itemVariants}
              icon={<BarChart2 className="w-6 h-6 text-primary" />}
              title="Dashboard"
              path="/dashboard"
            />
            <Link href="/knowledge">
            <QuickAccessCard
              variants={itemVariants}
              icon={<BookOpen className="w-6 h-6 text-primary" />}
              title="知识库"
              path="/knowledge"
            />
            </Link>
            <Link href="/procurement">
            <QuickAccessCard
              variants={itemVariants}
              icon={<Network className="w-6 h-6 text-primary" />}
              title="采购管理"
              path="/procurement"
            />
            </Link>
            <QuickAccessCard
              variants={itemVariants}
              icon={<FileText className="w-6 h-6 text-primary" />}
              title="模板中心"
              path="/knowledge/templates"
            />
            <QuickAccessCard
              variants={itemVariants}
              icon={<Layers className="w-6 h-6 text-primary" />}
              title="实体类型库"
              path="/entity-types"
            />
          </div>
        </motion.div>
      </main>

      {/* 底部版权 */}
      <footer className="relative z-10 bg-[#1a1a1a] dark:bg-[#1a1a1a] text-muted-foreground dark:text-muted-foreground py-8 text-center text-sm">
        <p>© 吉林化工工程有限公司 2026 v0.5.0</p>
      </footer>
    </div>
  );
}

function StatsCard({
  icon,
  number,
  title,
  desc,
  variants,
  accent = "primary",
}: {
  icon: React.ReactNode;
  number: string;
  title: string;
  desc: string;
  variants: Variants;
  accent?: "amber" | "emerald" | "violet" | "sky" | "primary";
}) {
  const accentColors: Record<string, { light: string; dark: string; glow: string }> = {
    amber:   { light: "bg-amber-50 border-amber-200 text-amber-600", dark: "dark:bg-amber-500/10 dark:border-amber-500/20 dark:text-amber-400", glow: "dark:shadow-amber-500/10" },
    emerald: { light: "bg-emerald-50 border-emerald-200 text-emerald-600", dark: "dark:bg-emerald-500/10 dark:border-emerald-500/20 dark:text-emerald-400", glow: "dark:shadow-emerald-500/10" },
    violet:  { light: "bg-violet-50 border-violet-200 text-violet-600", dark: "dark:bg-violet-500/10 dark:border-violet-500/20 dark:text-violet-400", glow: "dark:shadow-violet-500/10" },
    sky:     { light: "bg-sky-50 border-sky-200 text-sky-600", dark: "dark:bg-sky-500/10 dark:border-sky-500/20 dark:text-sky-400", glow: "dark:shadow-sky-500/10" },
    primary: { light: "bg-primary/10 border-primary/20 text-primary", dark: "dark:bg-primary/10 dark:border-primary/20 dark:text-primary", glow: "dark:shadow-primary/10" },
  };
  const a = (accentColors[accent] ?? accentColors.primary)!;

  return (
    <motion.div
      variants={variants}
      whileHover={{ y: -6, scale: 1.02 }}
      className="glass-card stats-card-glow rounded-3xl p-7 flex flex-col justify-between transition-all duration-300 hover:shadow-2xl cursor-pointer group"
    >
      {/* icon container — tinted per accent */}
      <div className={`w-11 h-11 rounded-2xl border flex items-center justify-center mb-5 transition-colors duration-300 ${a.light} ${a.dark}`}>
        {icon}
      </div>

      {/* stat body */}
      <div>
        <h3 className="text-[2.25rem] font-black text-foreground dark:text-white mb-1.5 tracking-tight tabular-nums leading-none">
          {number}
        </h3>
        <p className="text-sm font-semibold text-foreground/80 dark:text-white/80 mb-1">{title}</p>
        <p className="text-xs text-muted-foreground dark:text-white/45 leading-relaxed">{desc}</p>
      </div>

      {/* subtle bottom accent bar — visible on hover */}
      <div className={`mt-5 h-0.5 w-0 group-hover:w-full rounded-full transition-all duration-500 ease-out bg-gradient-to-r ${accent === "amber" ? "from-amber-400 to-amber-500" : accent === "emerald" ? "from-emerald-400 to-emerald-500" : accent === "violet" ? "from-violet-400 to-violet-500" : accent === "sky" ? "from-sky-400 to-sky-500" : "from-primary to-primary/60"}`} />
    </motion.div>
  );
}

function QuickAccessCard({
  icon,
  title,
  path,
  variants,
}: {
  icon: React.ReactNode;
  title: string;
  path: string;
  variants: Variants;
}) {
  return (
    <motion.div
      variants={variants}
      whileHover={{ y: -4 }}
      className="group relative bg-card dark:bg-card rounded-2xl p-6 flex items-center justify-between cursor-pointer transition-all duration-300 shadow-[0_4px_20px_rgba(0,0,0,0.03)] dark:shadow-[0_4px_20px_rgba(0,0,0,0.3)] hover:shadow-lg hover:shadow-primary/10 border border-transparent hover:border-primary/40 overflow-hidden"
    >
      {/* Hover时的左侧浅灰色粗边框 */}
      <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-muted-foreground/30 dark:bg-muted-foreground/30 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>

      <div className="flex items-center space-x-4 relative z-10">
        <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
          {icon}
        </div>
        <div>
          <h4 className="text-lg font-bold text-foreground dark:text-white mb-0.5">{title}</h4>
          <p className="text-sm text-muted-foreground dark:text-muted-foreground font-mono">{path}</p>
        </div>
      </div>

      <ArrowRight className="w-5 h-5 text-primary/40 group-hover:text-primary transition-colors relative z-10" />
    </motion.div>
  );
}
