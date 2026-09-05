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
  Settings,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import React, { useCallback, useState } from "react";
import { toast } from "sonner";

import "./index.css";
import { MobileNav } from "@/components/landing/mobile-nav";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Toaster } from "@/components/ui/sonner";
import { PermissionProvider, usePermission } from "@/core/permissions";
import { useAuth } from "@/extensions/hooks/useAuth";

export default function LandingNew() {
  const [mounted, setMounted] = useState(false);
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const handleNavClick = useCallback(
    (path: string) => {
      if (!user) {
        const redirect = encodeURIComponent(path);
        router.push(`/login?redirect=${redirect}`);
      } else {
        router.push(path);
      }
    },
    [user, router],
  );

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
    <div className="bg-background relative min-h-screen overflow-hidden font-sans dark:bg-[#0a0a0a]">
      <Toaster />
      {/* 科技感背景：网格与柔和光晕 */}
      <div className="pointer-events-none absolute inset-0 z-0">
        <div className="bg-grid-pattern absolute inset-0 opacity-60"></div>
        {/* 左下角蓝色光晕 */}
        <div className="bg-primary/10 absolute top-[40%] -left-[20%] h-[60%] w-[60%] rounded-full blur-[120px]"></div>
        {/* 右上角青色光晕 */}
        <div className="absolute -top-[10%] -right-[10%] h-[50%] w-[50%] rounded-full bg-teal-400/10 blur-[120px]"></div>
      </div>

      {/* 顶部导航栏 */}
      <nav className="bg-card/70 dark:bg-card/70 border-border dark:border-border relative z-10 flex items-center justify-between border-b px-8 py-4 backdrop-blur-md">
        <div className="flex items-center space-x-3">
          {/* Logo */}
          <img
            src="/favicon.svg"
            alt="Logo"
            className="h-auto w-8 object-contain"
          />
          <span className="text-primary text-xl font-bold tracking-wide">
            吉林化工工程有限公司
          </span>
        </div>

        <PermissionProvider>
          <NavItems onNavClick={handleNavClick} />
        </PermissionProvider>

        <div className="flex items-center">
          {!isLoading &&
            (user ? (
              mounted ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm whitespace-nowrap">
                      <UserCircle className="h-6 w-6" strokeWidth={1.5} />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    className="w-64 rounded-xl"
                    align="end"
                    sideOffset={8}
                  >
                    <div className="border-border dark:border-border border-b px-3 py-2">
                      <p className="text-foreground dark:text-foreground text-sm font-medium">
                        {user.username}
                      </p>
                      <p className="text-muted-foreground dark:text-muted-foreground text-xs">
                        {user.email}
                      </p>
                    </div>
                    <DropdownMenuGroup className="py-1">
                      <DropdownMenuItem
                        onClick={() => router.push("/settings")}
                      >
                        <Settings className="mr-2 h-4 w-4" />
                        配置
                      </DropdownMenuItem>
                    </DropdownMenuGroup>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={logout}
                      className="text-red-500 focus:text-red-500 dark:text-red-400 dark:focus:text-red-400"
                    >
                      <LogOutIcon className="mr-2 h-4 w-4" />
                      退出登录
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <div className="bg-primary/10 h-9 w-9 animate-pulse rounded-full" />
              )
            ) : (
              <button
                onClick={() => router.push("/login")}
                className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm whitespace-nowrap"
              >
                <LogIn className="h-4 w-4" />
                登录
              </button>
            ))}
        </div>
      </nav>

      {/* 主内容区 */}
      <main className="relative z-10 mx-auto max-w-7xl px-6 pt-20 pb-24">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 items-center gap-16 lg:grid-cols-2"
        >
          {/* 左侧：Hero 文本区 */}
          <div className="space-y-8">
            <motion.div variants={itemVariants}>
              <span className="bg-primary/10 text-primary border-primary/20 inline-flex items-center space-x-2 rounded-full border px-4 py-1.5 text-sm font-medium">
                <Sparkles className="h-4 w-4" />
                <span>企业智能体平台套件，融合知识工厂与RAG知识库</span>
              </span>
            </motion.div>

            <motion.div variants={itemVariants} className="space-y-6">
              <h1 className="text-foreground text-3xl leading-[1.15] font-extrabold tracking-tight md:text-6xl dark:text-white">
                吉林化工工程: 石化设计领域智能应用平台
              </h1>
              {/* 渐变装饰线 */}
              <div className="from-primary via-primary/70 h-1.5 w-full rounded-full bg-gradient-to-r to-teal-400"></div>
              <p className="text-muted-foreground dark:text-muted-foreground text-xl font-medium">
                统一编排 Agent、知识库、skills、MCP与工具链
              </p>
            </motion.div>

            <motion.div
              variants={itemVariants}
              className="flex flex-wrap gap-4 pt-4"
            >
              <PermissionProvider>
                <HeroActions onNavClick={handleNavClick} />
              </PermissionProvider>
            </motion.div>
          </div>

          {/* 右侧：数据统计卡片 */}
          <div className="relative grid grid-cols-1 gap-5 sm:grid-cols-2">
            {/* 装饰性背景 — subtle warm glow in light, cool glow in dark */}
            <div className="bg-primary/5 dark:bg-primary/[0.03] absolute -inset-10 -z-10 rounded-full blur-[100px]" />
            <div className="absolute top-1/2 left-1/2 -z-10 h-[60%] w-[120%] -translate-x-1/2 -translate-y-1/2 rounded-full bg-teal-400/5 blur-[80px] dark:bg-teal-400/[0.04]" />

            <StatsCard
              variants={itemVariants}
              icon={<Star className="h-5 w-5" />}
              number="2300+"
              title="知识量"
              desc="业务人员的参与与支持"
              accent="amber"
            />
            <StatsCard
              variants={itemVariants}
              icon={<CheckCircle2 className="h-5 w-5" />}
              number="200+"
              title="SKILLS数量"
              desc="持续改进和问题解决能力"
              accent="emerald"
            />
            <StatsCard
              variants={itemVariants}
              icon={<GitMerge className="h-5 w-5" />}
              number="50+"
              title="MCP数量"
              desc="活跃的开发迭代和功能更新"
              accent="violet"
            />
            <StatsCard
              variants={itemVariants}
              icon={<ShieldCheck className="h-5 w-5" />}
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
          <div className="mb-12 space-y-3 text-center">
            <motion.h2
              variants={itemVariants}
              className="text-foreground text-3xl font-bold dark:text-white"
            >
              快速访问
            </motion.h2>
            <motion.p
              variants={itemVariants}
              className="text-muted-foreground dark:text-muted-foreground"
            >
              探索平台核心功能模块
            </motion.p>
          </div>

          <PermissionProvider>
            <QuickAccessGrid variants={itemVariants} />
          </PermissionProvider>
        </motion.div>
      </main>

      {/* 底部版权 */}
      <footer className="text-muted-foreground dark:text-muted-foreground relative z-10 bg-[#1a1a1a] py-8 text-center text-sm dark:bg-[#1a1a1a]">
        <p>© 吉林化工工程有限公司 2026 v0.5.0</p>
      </footer>
    </div>
  );
}

// Hero 操作区：未登录只显示"欢迎登录"；登录后按 nav 权限过滤 开始写作/知识加工（与 NavItems 同套 canNav）
function HeroActions({ onNavClick }: { onNavClick: (path: string) => void }) {
  const { user, isLoading } = useAuth();
  const { canNav } = usePermission();

  if (isLoading) return null;
  if (!user) {
    return (
      <Link
        href="/login"
        className="bg-primary hover:bg-primary/90 text-primary-foreground shadow-primary/20 flex items-center space-x-2 rounded-xl px-8 py-3.5 font-medium shadow-lg transition-colors"
      >
        <LogIn className="h-5 w-5" />
        <span>欢迎登录</span>
      </Link>
    );
  }
  return (
    <>
      {canNav("nav:writing") && (
        <button
          onClick={() => onNavClick("/workspace/chats/new")}
          className="bg-primary hover:bg-primary/90 text-primary-foreground shadow-primary/20 flex items-center space-x-2 rounded-xl px-8 py-3.5 font-medium shadow-lg transition-colors"
        >
          <Rocket className="h-5 w-5" />
          <span>开始写作</span>
        </button>
      )}
      {canNav("nav:knowledge-factory") && (
        <button
          onClick={() => onNavClick("/knowledge-factory?tab=reports")}
          className="bg-card dark:bg-card hover:bg-primary/10 text-primary border-primary/30 hover:border-primary/50 hover:shadow-primary/15 flex items-center space-x-2 rounded-xl border px-8 py-3.5 font-medium shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:scale-[1.02] hover:shadow-md active:scale-[0.98]"
        >
          <FolderCog className="h-5 w-5" />
          <span>知识加工</span>
        </button>
      )}
    </>
  );
}

// 头部导航：未登录不显示；登录后按 /api/permissions/me 的 nav 权限过滤（与 Sidebar 同一套 canNav）
function NavItems({ onNavClick }: { onNavClick: (path: string) => void }) {
  const { user } = useAuth();
  const { canNav } = usePermission();

  const items = [
    { label: "工程报告", path: "/workspace/chats/new", navId: "nav:writing" },
    {
      label: "知识工厂",
      path: "/knowledge-factory?tab=reports",
      navId: "nav:knowledge-factory",
    },
    { label: "文档空间", path: "/docmgr", navId: "nav:docmgr" },
    { label: "应用中心", path: "/app-center", navId: "nav:app-center" },
  ];
  const visible = items.filter((item) => canNav(item.navId));

  if (!user) return null;
  return (
    <>
      <div className="text-muted-foreground dark:text-muted-foreground hidden items-center space-x-2 font-medium md:flex">
        {visible.map((item) => (
          <button
            key={item.path}
            onClick={() => onNavClick(item.path)}
            className="hover:bg-primary/10 hover:text-primary rounded-lg px-4 py-2 transition-all duration-200"
          >
            {item.label}
          </button>
        ))}
      </div>
      {visible.length > 0 && (
        <MobileNav
          links={visible.map((item) => ({
            href: item.path,
            label: item.label,
          }))}
        />
      )}
    </>
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
  const accentColors: Record<
    string,
    { light: string; dark: string; glow: string }
  > = {
    amber: {
      light: "bg-amber-50 border-amber-200 text-amber-600",
      dark: "dark:bg-amber-500/10 dark:border-amber-500/20 dark:text-amber-400",
      glow: "dark:shadow-amber-500/10",
    },
    emerald: {
      light: "bg-emerald-50 border-emerald-200 text-emerald-600",
      dark: "dark:bg-emerald-500/10 dark:border-emerald-500/20 dark:text-emerald-400",
      glow: "dark:shadow-emerald-500/10",
    },
    violet: {
      light: "bg-violet-50 border-violet-200 text-violet-600",
      dark: "dark:bg-violet-500/10 dark:border-violet-500/20 dark:text-violet-400",
      glow: "dark:shadow-violet-500/10",
    },
    sky: {
      light: "bg-sky-50 border-sky-200 text-sky-600",
      dark: "dark:bg-sky-500/10 dark:border-sky-500/20 dark:text-sky-400",
      glow: "dark:shadow-sky-500/10",
    },
    primary: {
      light: "bg-primary/10 border-primary/20 text-primary",
      dark: "dark:bg-primary/10 dark:border-primary/20 dark:text-primary",
      glow: "dark:shadow-primary/10",
    },
  };
  const a = (accentColors[accent] ?? accentColors.primary)!;

  return (
    <motion.div
      variants={variants}
      whileHover={{ y: -6, scale: 1.02 }}
      className="glass-card stats-card-glow group flex cursor-pointer flex-col justify-between rounded-3xl p-7 transition-all duration-300 hover:shadow-2xl"
    >
      {/* icon container — tinted per accent */}
      <div
        className={`mb-5 flex h-11 w-11 items-center justify-center rounded-2xl border transition-colors duration-300 ${a.light} ${a.dark}`}
      >
        {icon}
      </div>

      {/* stat body */}
      <div>
        <h3 className="text-foreground mb-1.5 text-[2.25rem] leading-none font-black tracking-tight tabular-nums dark:text-white">
          {number}
        </h3>
        <p className="text-foreground/80 mb-1 text-sm font-semibold dark:text-white/80">
          {title}
        </p>
        <p className="text-muted-foreground text-xs leading-relaxed dark:text-white/45">
          {desc}
        </p>
      </div>

      {/* subtle bottom accent bar — visible on hover */}
      <div
        className={`mt-5 h-0.5 w-0 rounded-full bg-gradient-to-r transition-all duration-500 ease-out group-hover:w-full ${accent === "amber" ? "from-amber-400 to-amber-500" : accent === "emerald" ? "from-emerald-400 to-emerald-500" : accent === "violet" ? "from-violet-400 to-violet-500" : accent === "sky" ? "from-sky-400 to-sky-500" : "from-primary to-primary/60"}`}
      />
    </motion.div>
  );
}

interface QuickAccessCardData {
  title: string;
  path: string;
  icon: React.ReactNode;
  navId?: string;
  adminOnly?: boolean;
}

// 快速访问区：未登录置灰不可点；登录后按 nav 权限/管理员判权，无权限 toast 提示
function QuickAccessGrid({ variants }: { variants: Variants }) {
  const { user } = useAuth();
  const { canNav, is_admin } = usePermission();
  const router = useRouter();

  const cards: QuickAccessCardData[] = [
    {
      title: "Dashboard",
      path: "/dashboard",
      navId: "nav:dashboard",
      icon: <BarChart2 className="text-primary h-6 w-6" />,
    },
    {
      title: "知识库",
      path: "/knowledge",
      navId: "nav:knowledge",
      icon: <BookOpen className="text-primary h-6 w-6" />,
    },
    {
      title: "文档中心",
      path: "/docmgr",
      navId: "nav:docmgr",
      icon: <FileText className="text-primary h-6 w-6" />,
    },
    {
      title: "API接口查询",
      path: "/docs",
      adminOnly: true,
      icon: <Layers className="text-primary h-6 w-6" />,
    },
    {
      title: "系统管理",
      path: "/admin",
      adminOnly: true,
      navId: "nav:admin",
      icon: <Network className="text-primary h-6 w-6" />,
    },
  ];

  const isAllowed = (card: QuickAccessCardData) => {
    if (card.adminOnly && !is_admin) return false;
    if (card.navId && !canNav(card.navId)) return false;
    return true;
  };

  const handleClick = (card: QuickAccessCardData) => {
    if (!user) return; // 登录前不可点击
    if (!isAllowed(card)) {
      toast.error("没有权限");
      return;
    }
    router.push(card.path);
  };

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => (
        <QuickAccessCard
          key={card.title}
          variants={variants}
          icon={card.icon}
          title={card.title}
          path={card.path}
          onClick={() => handleClick(card)}
          disabled={!user}
        />
      ))}
    </div>
  );
}

function QuickAccessCard({
  icon,
  title,
  path,
  variants,
  onClick,
  disabled,
}: {
  icon: React.ReactNode;
  title: string;
  path: string;
  variants: Variants;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <motion.div
      variants={variants}
      whileHover={disabled ? undefined : { y: -4 }}
      onClick={onClick}
      className={
        "group bg-card dark:bg-card border-border dark:border-border relative flex items-center justify-between overflow-hidden rounded-2xl border p-6 shadow-[0_4px_20px_rgba(0,0,0,0.03)] transition-all duration-300 dark:shadow-[0_4px_20px_rgba(0,0,0,0.3)] " +
        (disabled
          ? "cursor-not-allowed opacity-60"
          : "hover:shadow-primary/10 hover:border-primary/40 cursor-pointer hover:shadow-lg")
      }
    >
      {/* Hover时的左侧主色竖线（与 hover 边框同色系） */}
      <div className="bg-primary/70 dark:bg-primary/70 absolute top-0 bottom-0 left-0 w-1.5 opacity-0 transition-opacity duration-300 group-hover:opacity-100"></div>

      <div className="relative z-10 flex items-center space-x-4">
        <div className="bg-primary/10 group-hover:bg-primary/20 flex h-14 w-14 items-center justify-center rounded-2xl transition-colors">
          {icon}
        </div>
        <div>
          <h4 className="text-foreground mb-0.5 text-lg font-bold dark:text-white">
            {title}
          </h4>
          <p className="text-muted-foreground dark:text-muted-foreground font-mono text-sm">
            {path}
          </p>
        </div>
      </div>

      <ArrowRight className="text-primary/40 group-hover:text-primary relative z-10 h-5 w-5 transition-colors" />
    </motion.div>
  );
}
