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
import { useRouter } from "next/navigation";
import Link from "next/link";
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
    <div className="min-h-screen relative bg-slate-50 overflow-hidden font-sans"> 
      {/* 科技感背景：网格与柔和光晕 */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 bg-grid-pattern opacity-60"></div>
        {/* 左下角蓝色光晕 */}
        <div className="absolute -left-[20%] top-[40%] w-[60%] h-[60%] rounded-full bg-primary/10 blur-[120px]"></div>
        {/* 右上角青色光晕 */}
        <div className="absolute -right-[10%] -top-[10%] w-[50%] h-[50%] rounded-full bg-teal-400/10 blur-[120px]"></div>
      </div>

      {/* 顶部导航栏 */}
      <nav className="relative z-10 flex items-center justify-between px-8 py-4 bg-white/70 backdrop-blur-md border-b border-slate-200/50">
        <div className="flex items-center space-x-3">
          {/* Logo */}
          <img
            src="/favicon.svg"
            alt="Logo"
            className="w-8 h-auto object-contain"
          />
          <span className="text-xl font-bold text-primary tracking-wide">
            北京华宇工程有限公司
          </span>
        </div>

        <div className="hidden md:flex items-center space-x-2 text-gray-600 font-medium">
          <button onClick={() => handleNavClick("/workspace/chats/new")} className="px-4 py-2 rounded-lg hover:bg-primary/10 hover:text-primary transition-all duration-200">工程报告</button>
          <button onClick={() => handleNavClick("/knowledge-factory?tab=reports")} className="px-4 py-2 rounded-lg hover:bg-primary/10 hover:text-primary transition-all duration-200">知识工厂</button>
          <button onClick={() => handleNavClick("/docmgr")} className="px-4 py-2 rounded-lg hover:bg-primary/10 hover:text-primary transition-all duration-200">文档空间</button>
          <button onClick={() => handleNavClick("/settings")} className="px-4 py-2 rounded-lg hover:bg-primary/10 hover:text-primary transition-all duration-200">设置</button>
        </div>

        <div className="flex items-center">
          {!isLoading && (
            user ? (
              mounted ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="flex items-center justify-center w-9 h-9 rounded-full bg-primary/10 hover:bg-primary/20 text-gray-600 hover:text-primary transition-all duration-200">
                      <UserCircle className="w-6 h-6" strokeWidth={1.5} />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent className="w-64 rounded-xl" align="end" sideOffset={8}>
                    <div className="px-3 py-2 border-b border-gray-100">
                      <p className="text-sm font-medium text-gray-900">{user.username}</p>
                      <p className="text-xs text-gray-500">{user.email}</p>
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
                    <DropdownMenuItem onClick={logout} className="text-red-600 focus:text-red-600">
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
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary transition-all duration-200 font-medium"
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
                <span>Harness驱动的Agent平台</span>
              </span>
            </motion.div>

            <motion.div variants={itemVariants} className="space-y-6">
              <h1 className="text-3xl md:text-6xl font-extrabold text-gray-900 leading-[1.15] tracking-tight">
                华宇工程: 煤矿设计领域智能应用平台
              </h1>
              {/* 渐变装饰线 */}
              <div className="h-1.5 w-full bg-gradient-to-r from-primary via-primary/70 to-teal-400 rounded-full"></div>
              <p className="text-xl text-gray-600 font-medium">
                Harness驱动的智能体平台
              </p>
            </motion.div>

            <motion.div variants={itemVariants} className="flex flex-wrap gap-4 pt-4">
              <button
                onClick={() => handleNavClick("/workspace/chats/new")}
                className="flex items-center space-x-2 px-8 py-3.5 bg-primary hover:bg-primary/90 text-white rounded-xl font-medium shadow-lg shadow-primary/20 transition-colors"
              >
                <Rocket className="w-5 h-5" />
                <span>开始写作</span>
              </button>
              <button
                onClick={() => handleNavClick("/knowledge-factory?tab=reports")}
                className="flex items-center space-x-2 px-8 py-3.5 bg-white hover:bg-primary/10 text-primary border border-primary/30 hover:border-primary/50 rounded-xl font-medium shadow-sm transition-all duration-200 hover:shadow-md hover:shadow-primary/15 hover:scale-[1.02] hover:-translate-y-0.5 active:scale-[0.98]"
              >
                <FolderCog className="w-5 h-5" />
                <span>知识加工</span>
              </button>
            </motion.div>
          </div>

          {/* 右侧：数据统计卡片 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 relative">
            {/* 装饰性背景 */}
            <div className="absolute inset-0 bg-white/40 blur-3xl rounded-full -z-10"></div>

            <StatsCard
              variants={itemVariants}
              icon={<Star className="w-6 h-6 text-primary" />}
              number="2300+"
              title="知识量"
              desc="业务人员的参与与支持"
            />
            <StatsCard
              variants={itemVariants}
              icon={<CheckCircle2 className="w-6 h-6 text-primary" />}
              number="200+"
              title="SKILLS数量"
              desc="持续改进和问题解决能力"
            />
            <StatsCard
              variants={itemVariants}
              icon={<GitMerge className="w-6 h-6 text-primary" />}
              number="50+"
              title="MCP数量"
              desc="活跃的开发迭代和功能更新"
            />
            <StatsCard
              variants={itemVariants}
              icon={<ShieldCheck className="w-6 h-6 text-primary" />}
              number="10+"
              title="报告种类"
              desc="煤炭行业工程设计类报告生成"
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
            <motion.h2 variants={itemVariants} className="text-3xl font-bold text-gray-900">
              快速访问
            </motion.h2>
            <motion.p variants={itemVariants} className="text-gray-600">
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
      <footer className="relative z-10 bg-[#1a1a1a] text-gray-400 py-8 text-center text-sm">
        <p>© 北京华宇工程有限公司 2026 v0.5.0</p>
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
}: {
  icon: React.ReactNode;
  number: string;
  title: string;
  desc: string;
  variants: Variants;
}) {
  return (
    <motion.div
      variants={variants}
      whileHover={{ y: -4 }}
      className="glass-card rounded-3xl p-8 flex flex-col justify-between transition-all duration-300 hover:border-primary/50 hover:shadow-xl hover:shadow-primary/20 cursor-pointer"
    >
      <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center mb-6">
        {icon}
      </div>
      <div>
        <h3 className="text-4xl font-black text-gray-900 mb-2 tracking-tight">{number}</h3>
        <p className="text-sm font-bold text-gray-600 mb-1">{title}</p>
        <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
      </div>
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
      className="group relative bg-white rounded-2xl p-6 flex items-center justify-between cursor-pointer transition-all duration-300 shadow-[0_4px_20px_rgba(0,0,0,0.03)] hover:shadow-lg hover:shadow-primary/10 border border-transparent hover:border-primary/40 overflow-hidden"
    >
      {/* Hover时的左侧浅灰色粗边框 */}
      <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-gray-300 opacity-0 group-hover:opacity-100 transition-opacity duration-300 dark:bg-gray-600"></div>

      <div className="flex items-center space-x-4 relative z-10">
        <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
          {icon}
        </div>
        <div>
          <h4 className="text-lg font-bold text-gray-900 mb-0.5">{title}</h4>
          <p className="text-sm text-gray-500 font-mono">{path}</p>
        </div>
      </div>

      <ArrowRight className="w-5 h-5 text-primary/40 group-hover:text-primary transition-colors relative z-10" />
    </motion.div>
  );
}
