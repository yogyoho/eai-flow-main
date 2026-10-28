"use client";

// EAI-CUSTOM: landing-v2 —— 2026-09-26 重设计版营销落地页（方案 B：登录感知双形态）。
// 设计目标：large hero + 单一 CTA（营销态）+ 产品视觉；登录后追加权限过滤的快速访问带与用户菜单。
// 设计文档：docs/designs/2026-09-26-landing-v2-optimization.md（2026-09-26 用户拍板 B）。
// 独立模块：不覆盖 components/landing-new（/ 路由仍指向 landing-new，本页挂 /landing-v2）。
// 样式约束：全语义 token（docs/designs/ui-style-spec §5），无独立 CSS 文件，暗色自适应；图标 lucide 线框。

import { motion, type Variants } from "framer-motion";
import {
  ArrowRight,
  BarChart2,
  BookOpen,
  CheckCircle2,
  FileText,
  FolderCog,
  Layers,
  LayoutGrid,
  Loader2,
  Lock,
  LogOutIcon,
  Rocket,
  Settings,
  ShieldCheck,
  Sparkles,
  UserCircle,
} from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useCallback, useEffect, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuGroup,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PermissionProvider, usePermission } from "@/core/permissions";
import { useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";

/** 首屏统一入场：淡入 + 上移，子元素级联错峰 */
const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.12, delayChildren: 0.1 },
  },
};

const itemVariants: Variants = {
  hidden: { y: 24, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: { type: "spring" as const, stiffness: 90, damping: 16 },
  },
};

/** 信任数据行：数字口径与 landing-new 一致，desc 语境行从 landing-new StatsCard 迁移（P1-3） */
const STATS = [
  { value: "2300+", label: "行业知识条目", desc: "业务人员的参与与支持" },
  { value: "200+", label: "内置技能", desc: "持续改进和问题解决能力" },
  { value: "50+", label: "MCP 工具链", desc: "活跃的开发迭代和功能更新" },
  {
    value: "10+",
    label: "报告种类",
    desc: "煤炭行业工程设计类报告生成",
  },
];

/** 快速访问带（登录态）：复用 landing-new 的判权口径（navId → canNav，adminOnly → is_admin） */
interface WorkbandItem {
  title: string;
  desc: string;
  path: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  navId?: string;
  adminOnly?: boolean;
}

const WORKBAND_ITEMS: WorkbandItem[] = [
  {
    title: "工程报告",
    desc: "对话直达专业报告交付",
    path: "/workspace/chats/new",
    icon: Rocket,
    navId: "nav:writing",
  },
  {
    title: "知识工厂",
    desc: "样例抽取 · 模板沉淀",
    path: "/knowledge-factory?tab=reports",
    icon: FolderCog,
    navId: "nav:knowledge-factory",
  },
  {
    title: "文档空间",
    desc: "项目文档与团队协作",
    path: "/docmgr",
    icon: FileText,
    navId: "nav:docmgr",
  },
  {
    title: "应用中心",
    desc: "扩展应用与集成",
    path: "/app-center",
    icon: LayoutGrid,
    navId: "nav:app-center",
  },
  {
    title: "知识库",
    desc: "RAG 检索与知识管理",
    path: "/knowledge",
    icon: BookOpen,
    navId: "nav:knowledge",
  },
  {
    title: "仪表盘",
    desc: "经营与平台运行数据",
    path: "/dashboard",
    icon: BarChart2,
    navId: "nav:dashboard",
  },
  {
    title: "API 接口",
    desc: "接口查询（管理员）",
    path: "/docs",
    icon: Layers,
    adminOnly: true,
  },
  {
    title: "系统管理",
    desc: "用户 · 角色 · 策略",
    path: "/admin",
    icon: ShieldCheck,
    adminOnly: true,
    navId: "nav:admin",
  },
];

export default function LandingV2() {
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();
  // 与 landing-new 同款：user 相关 UI 等 mount 后再渲染，避免 SSR/客户端不一致
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  /** 全页唯一 CTA：未登录去登录页，已登录进工作台 */
  const go = useCallback(() => {
    router.push(user ? "/workspace" : "/login");
  }, [user, router]);

  return (
    // 注意：根容器不可加 overflow-hidden——会破坏 sticky 顶栏；光晕裁剪收敛到内层 absolute 包装
    <div className="bg-background relative min-h-screen font-sans">
      {/* 背景组合层：渐变打底 + 点阵纹理 + 光晕，全部 token 衍生色（color-mix 引用 --color-primary，非硬编码），暗色自适应；overflow-hidden 只作用于本层 */}
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
        {/* 打底渐变：顶部极淡主色洗染，消除纯白/纯黑的平板感 */}
        <div className="from-primary/[0.06] via-background to-background absolute inset-0 bg-gradient-to-b" />
        {/* 点阵网格：主色 token 上色，顶部聚焦、向下渐隐（mask 中 black 为遮罩不透明度约定色，非页面用色） */}
        <div className="absolute inset-0 [background-image:radial-gradient(color-mix(in_oklab,var(--color-primary)_16%,transparent)_1px,transparent_1px)] [background-size:26px_26px] [mask-image:radial-gradient(120%_60%_at_50%_0%,black_10%,transparent_70%)]" />
        {/* 光晕：主色主光 + info 次级色 + 底部双角弱光 */}
        <div className="bg-primary/15 absolute -top-[15%] left-1/2 h-[45rem] w-[70rem] -translate-x-1/2 rounded-full blur-[140px]" />
        <div className="bg-info/10 absolute top-[28%] right-[-12%] h-[32rem] w-[36rem] rounded-full blur-[120px]" />
        <div className="bg-primary/[0.08] absolute right-[-10%] bottom-[-15%] h-[40rem] w-[40rem] rounded-full blur-[130px]" />
        <div className="bg-primary/5 absolute bottom-[-10%] left-[-12%] h-[30rem] w-[30rem] rounded-full blur-[120px]" />
      </div>

      {/* 顶栏：logo + 单一 CTA（未登录）/ 用户菜单（已登录） */}
      <nav className="bg-background/70 border-border/60 sticky top-0 z-20 border-b backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <img
              src="/favicon.svg"
              alt="中交三公局智能体平台"
              className="h-8 w-8 object-contain"
            />
            <span className="text-foreground text-base font-semibold tracking-wide">
              中交三公局
            </span>
          </div>
          <div className="flex items-center">
            {isLoading ? (
              // 加载占位：与 landing-new 同款骨架，保证 SSR/客户端首帧一致
              <div className="bg-primary/10 h-9 w-24 animate-pulse rounded-xl" />
            ) : user ? (
              mounted ? (
                <UserMenu username={user.username} onLogout={logout} />
              ) : (
                <div className="bg-primary/10 h-9 w-9 animate-pulse rounded-full" />
              )
            ) : (
              <CtaButton size="sm" onClick={go} />
            )}
          </div>
        </div>
      </nav>

      <main className="relative z-10">
        {/* ===== 大 Hero：徽章 → 价值主张 → 副文案 → 唯一 CTA ===== */}
        <motion.section
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="mx-auto max-w-6xl px-6 pt-20 pb-16 text-center md:pt-28 md:pb-20"
        >
          <motion.div variants={itemVariants} className="flex justify-center">
            <span className="border-primary/20 bg-primary/10 text-primary inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-medium">
              <Sparkles className="h-4 w-4" />
              企业级智能体平台 · 知识工厂 × RAG 知识库
            </span>
          </motion.div>

          <motion.h1
            variants={itemVariants}
            className="text-foreground mx-auto mt-8 max-w-3xl text-4xl leading-[1.1] font-bold tracking-tight md:text-6xl"
          >
            从一句话，
            <br className="hidden md:block" />
            到一份专业交付
          </motion.h1>

          {/* 副文案锚定行业语境（P1-2）：矿山/煤炭工程 + 平台能力一句话 */}
          <motion.p
            variants={itemVariants}
            className="text-muted-foreground mx-auto mt-6 max-w-2xl text-lg leading-relaxed md:text-xl"
          >
            面向矿山与煤炭工程领域，统一编排智能体、知识库、技能与 MCP
            工具链——工程报告生成、知识加工与文档协作，从需求直达交付。
          </motion.p>

          <motion.div
            variants={itemVariants}
            className="mt-10 flex flex-col items-center gap-3"
          >
            <CtaButton size="lg" onClick={go} />
            {/* 差异点 + 企业信任一行带（P1-4 / P2-5）：回答「这跟直接问大模型有什么区别」 */}
            <span className="text-muted-foreground text-xs">
              不止对话——200+ 行业技能 · 规范库检索 · 可溯源交付 · 数据不出内网
            </span>
          </motion.div>
        </motion.section>

        {/* ===== 产品视觉：工作台 mockup + 信任数据行 ===== */}
        <section className="mx-auto max-w-6xl px-6 pb-24">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.7, ease: "easeOut" }}
          >
            <ProductVisual />
          </motion.div>

          {/* 信任数据行（非卡片，弱于 CTA 视觉层级） */}
          <motion.dl
            variants={containerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            className="mt-16 grid grid-cols-2 gap-x-8 gap-y-8 lg:grid-cols-4"
          >
            {STATS.map((s) => (
              <motion.div
                key={s.label}
                variants={itemVariants}
                className="flex flex-col items-center gap-1 text-center"
              >
                <div className="flex items-baseline gap-2">
                  <dt className="sr-only">{s.label}</dt>
                  <dd className="text-foreground text-2xl font-bold tabular-nums">
                    {s.value}
                  </dd>
                  <dd className="text-foreground/80 text-sm font-medium">
                    {s.label}
                  </dd>
                </div>
                <dd className="text-muted-foreground text-xs">{s.desc}</dd>
              </motion.div>
            ))}
          </motion.dl>
        </section>

        {/* ===== 登录态快速访问带（P0-1）：权限过滤，未登录不渲染 ===== */}
        {user && (
          <PermissionProvider>
            <Workband />
          </PermissionProvider>
        )}
      </main>

      <footer className="border-border/60 text-muted-foreground relative z-10 border-t py-8 text-center text-xs">
        © 中交三公局 2026 · v0.5.0
      </footer>
    </div>
  );
}

/** 单一 CTA 按钮：sm（顶栏）/ lg（Hero）两档 */
function CtaButton({
  size,
  onClick,
}: {
  size: "sm" | "lg";
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group bg-primary hover:bg-primary/90 text-primary-foreground shadow-primary/25 inline-flex items-center gap-2 rounded-xl font-medium shadow-lg transition-all duration-200 hover:shadow-xl active:scale-[0.98]",
        size === "lg" ? "px-8 py-3.5 text-base" : "px-5 py-2 text-sm",
      )}
    >
      开始使用
      <ArrowRight
        className={size === "lg" ? "h-5 w-5" : "h-4 w-4"}
        strokeWidth={1.5}
      />
    </button>
  );
}

/** 用户菜单（登录态顶栏）：镜像 landing-new 的下拉（配置/退出），不含权限项 */
function UserMenu({
  username,
  onLogout,
}: {
  username: string;
  onLogout: () => void;
}) {
  const router = useRouter();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          aria-label="用户菜单"
          className="text-muted-foreground hover:text-foreground inline-flex items-center"
        >
          <UserCircle className="h-6 w-6" strokeWidth={1.5} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56 rounded-xl" align="end" sideOffset={8}>
        <div className="border-border border-b px-3 py-2">
          <p className="text-foreground text-sm font-medium">{username}</p>
        </div>
        <DropdownMenuGroup className="py-1">
          <DropdownMenuItem onClick={() => router.push("/settings")}>
            <Settings className="mr-2 h-4 w-4" />
            配置
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={onLogout}
          className="text-red-500 focus:text-red-500 dark:text-red-400 dark:focus:text-red-400"
        >
          <LogOutIcon className="mr-2 h-4 w-4" />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** 快速访问带外壳：标题 + 权限过滤网格（Provider 在父级挂好，此处消费 usePermission） */
function Workband() {
  return (
    <motion.section
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="border-border/60 mx-auto max-w-6xl border-t px-6 py-16"
    >
      <div className="mb-10 space-y-2 text-center">
        <h2 className="text-foreground text-xl font-semibold">快速访问</h2>
        <p className="text-muted-foreground text-sm">
          按你的权限可直接进入的模块
        </p>
      </div>
      <WorkbandGrid />
    </motion.section>
  );
}

function WorkbandGrid() {
  const { canNav, is_admin } = usePermission();
  const router = useRouter();

  const visible = WORKBAND_ITEMS.filter((item) => {
    if (item.adminOnly && !is_admin) return false;
    if (item.navId && !canNav(item.navId)) return false;
    return true;
  });

  // 全部无权限（理论上罕见）→ 整块不渲染，避免空壳
  if (visible.length === 0) return null;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {visible.map((item) => (
        <button
          key={item.title}
          onClick={() => router.push(item.path)}
          className="group border-border bg-card hover:border-primary/40 hover:shadow-primary/10 flex flex-col gap-3 rounded-2xl border p-5 text-left shadow-[0_2px_12px_rgba(0,0,0,0.03)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg dark:shadow-[0_2px_12px_rgba(0,0,0,0.25)]"
        >
          <div className="flex items-center justify-between">
            <span className="bg-primary/10 text-primary flex h-10 w-10 items-center justify-center rounded-xl">
              <item.icon className="h-5 w-5" strokeWidth={1.5} />
            </span>
            <ArrowRight className="text-primary/30 group-hover:text-primary h-4 w-4 transition-colors" />
          </div>
          <div>
            <p className="text-foreground text-base font-semibold">
              {item.title}
            </p>
            <p className="text-muted-foreground mt-0.5 text-xs">{item.desc}</p>
          </div>
        </button>
      ))}
    </div>
  );
}

const RAIL_ITEMS = [
  { icon: FileText, label: "工程报告" },
  { icon: FolderCog, label: "知识工厂" },
  { icon: BookOpen, label: "知识库" },
  { icon: BarChart2, label: "仪表盘" },
  { icon: Settings, label: "设置" },
];

const AGENT_STEPS = [
  { done: true, text: "已检索知识库 · 命中 12 篇行业规范" },
  { done: true, text: "大纲已生成 · 8 章 41 节" },
  { done: false, text: "正在撰写「第 2 章 火灾危险性与防火等级」" },
];

const DOC_CHAPTERS = [
  "1 总则",
  "2 火灾危险性与防火等级",
  "3 消防设施设计",
  "4 消防给水与灭火系统",
  "5 防烟排烟与暖通防火",
  "6 消防电气与应急照明",
];

/** 产品视觉：浏览器窗框内手绘工作台（侧栏 + 对话流 + 交付物面板），全 token 配色 */
function ProductVisual() {
  return (
    <div className="relative mx-auto max-w-5xl">
      {/* 视觉后方光晕 */}
      <div className="bg-primary/15 absolute -inset-x-10 -top-10 bottom-0 -z-10 rounded-[2rem] blur-[80px]" />

      <div className="border-border bg-card shadow-2xl overflow-hidden rounded-2xl border">
        {/* 浏览器 chrome 条 */}
        <div className="bg-muted/50 border-border flex items-center gap-3 border-b px-4 py-3">
          <div className="flex gap-1.5" aria-hidden>
            <span className="bg-destructive/70 h-3 w-3 rounded-full" />
            <span className="bg-warning/70 h-3 w-3 rounded-full" />
            <span className="bg-success/70 h-3 w-3 rounded-full" />
          </div>
          <div className="border-border bg-background text-muted-foreground mx-auto flex items-center gap-1.5 rounded-full border px-4 py-1 text-xs">
            <Lock className="h-3 w-3" aria-hidden />
            eai-flow · 工作台
          </div>
          {/* 占位平衡 mx-auto 居中 */}
          <div className="w-14" aria-hidden />
        </div>

        {/* 应用主体：图标侧栏 + 对话流 + 交付物面板 */}
        <div className="grid h-[24rem] grid-cols-[2.75rem_1fr] md:h-[26rem] lg:grid-cols-[3rem_1fr_17rem]">
          {/* 图标侧栏 */}
          <div className="border-border/60 flex flex-col items-center gap-1 border-r py-4">
            <span className="bg-primary/10 text-primary mb-3 flex h-8 w-8 items-center justify-center rounded-lg">
              <Sparkles className="h-4 w-4" aria-hidden />
            </span>
            {RAIL_ITEMS.map(({ icon: Icon, label }) => (
              <span
                key={label}
                title={label}
                aria-label={label}
                className="text-muted-foreground hover:bg-muted hover:text-foreground flex h-8 w-8 cursor-default items-center justify-center rounded-lg transition-colors"
              >
                <Icon className="h-4 w-4" strokeWidth={1.5} aria-hidden />
              </span>
            ))}
          </div>

          {/* 对话流 */}
          <div className="flex flex-col gap-4 overflow-hidden p-4 md:p-5">
            <div className="bg-primary text-primary-foreground max-w-[80%] self-end rounded-2xl rounded-br-md px-4 py-2.5 text-sm">
              帮我起草一份矿井消防设施设计专篇的初稿
            </div>
            <div className="border-border bg-muted/40 max-w-[88%] space-y-2.5 rounded-2xl rounded-bl-md border p-4">
              <div className="text-foreground flex items-center gap-2 text-sm font-medium">
                <Sparkles className="text-primary h-4 w-4" aria-hidden />
                智能体正在工作
              </div>
              {AGENT_STEPS.map((step) => (
                <div
                  key={step.text}
                  className="text-muted-foreground flex items-center gap-2 text-xs"
                >
                  {step.done ? (
                    <CheckCircle2
                      className="text-success h-3.5 w-3.5 shrink-0"
                      aria-hidden
                    />
                  ) : (
                    <Loader2
                      className="text-primary h-3.5 w-3.5 shrink-0 animate-spin"
                      aria-hidden
                    />
                  )}
                  <span className={step.done ? "" : "text-foreground"}>
                    {step.text}
                  </span>
                </div>
              ))}
            </div>
            {/* 输入框示意：点出「一句话需求」的入口形态 */}
            <div className="border-border bg-background mt-auto flex items-center justify-between gap-3 rounded-2xl border px-4 py-3 shadow-sm">
              <span className="text-muted-foreground text-sm">
                输入需求，例如：生成给排水计算书…
              </span>
              <span className="bg-primary text-primary-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
                <ArrowRight className="h-4 w-4" aria-hidden />
              </span>
            </div>
          </div>

          {/* 交付物面板（窄屏隐藏） */}
          <div className="border-border/60 hidden flex-col gap-3 border-l p-4 lg:flex">
            <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
              <FileText className="h-3.5 w-3.5" aria-hidden />
              交付物预览
            </div>
            <div className="border-border bg-background flex-1 rounded-lg border p-3">
              <p className="text-foreground text-sm font-semibold">
                矿井消防设施设计专篇
              </p>
              <div className="mt-3 space-y-2.5">
                {DOC_CHAPTERS.map((c) => (
                  <div key={c} className="flex items-center gap-2">
                    <CheckCircle2
                      className="text-success h-3 w-3 shrink-0"
                      aria-hidden
                    />
                    <span className="text-muted-foreground truncate text-xs">
                      {c}
                    </span>
                  </div>
                ))}
              </div>
              {/* 图表占位 */}
              <div className="mt-4 flex h-16 items-end gap-1.5" aria-hidden>
                {[5, 9, 7, 12, 10, 14].map((h, i) => (
                  <div
                    key={i}
                    style={{ height: `${h * 4}px` }}
                    className={
                      i === 5
                        ? "bg-primary w-full rounded-sm"
                        : "bg-primary/20 w-full rounded-sm"
                    }
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 悬浮结果徽章：制造纵深；文案中性化（P2-6），不写编造数字 */}
      <motion.div
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        className="border-border bg-background absolute -bottom-5 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-xl border px-4 py-2.5 shadow-lg"
      >
        <CheckCircle2 className="text-success h-4 w-4" aria-hidden />
        <span className="text-foreground text-sm font-medium">
          报告已生成 · 已同步至文档空间
        </span>
      </motion.div>
    </div>
  );
}
