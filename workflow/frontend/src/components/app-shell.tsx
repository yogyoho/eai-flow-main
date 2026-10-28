"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ClipboardList,
  FileText,
  GitBranch,
  LayoutDashboard,
  Sparkles,
  Workflow,
} from "lucide-react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cn, initials } from "@/lib/utils";

const NAV = [
  {
    href: "/",
    label: "流程定义",
    description: "建模与发布",
    icon: LayoutDashboard,
    exact: true,
  },
  {
    href: "/tasks",
    label: "我的待办",
    description: "审批与流转",
    icon: ClipboardList,
    badge: "tasks" as const,
  },
  {
    href: "/instances",
    label: "流程实例",
    description: "运行与追踪",
    icon: GitBranch,
  },
  {
    href: "/forms",
    label: "表单中心",
    description: "业务表单",
    icon: FileText,
  },
];

function stripBasePath(pathname: string): string {
  if (pathname === "/workflow") return "/";
  if (pathname.startsWith("/workflow/")) return pathname.slice("/workflow".length);
  return pathname;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = stripBasePath(usePathname());
  const { user, users, switchUser } = useSession();

  const tasksQuery = useQuery({
    queryKey: ["tasks", "count", user.handler],
    queryFn: () => api.tasks.list({ page: 1, size: 100 }),
    refetchInterval: 30_000,
  });

  const pending = tasksQuery.data?.total ?? 0;

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col border-r border-border bg-sidebar lg:flex">
        <div className="flex h-[74px] items-center gap-3 px-5">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#3f7bff] to-[#1f4fd8] text-white shadow-[0_6px_16px_-6px_rgba(47,111,237,0.75)]">
            <Workflow className="h-[21px] w-[21px]" strokeWidth={2.2} />
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border-2 border-white bg-emerald-400" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-[15px] font-semibold tracking-tight">Flow Studio</p>
            <p className="truncate text-[11px] tracking-wide text-muted-foreground">
              EAI 工作流中台
            </p>
          </div>
        </div>

        <div className="px-3 pb-2 pt-3">
          <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground/70">
            工作台
          </p>
          <nav className="space-y-1">
            {NAV.map((item) => {
              const active = item.exact
                ? pathname === item.href
                : pathname.startsWith(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-colors",
                    active
                      ? "bg-sidebar-active font-medium text-primary"
                      : "text-sidebar-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary" />
                  )}
                  <Icon
                    className={cn(
                      "h-[17px] w-[17px]",
                      active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
                    )}
                    strokeWidth={2}
                  />
                  <span className="flex-1">{item.label}</span>
                  {item.badge === "tasks" && pending > 0 && (
                    <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-semibold text-white">
                      {pending > 99 ? "99+" : pending}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="mx-5 mt-4 rounded-xl border border-dashed border-primary/25 bg-primary/[0.035] p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            经典流程设计器
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
            LogicFlow 自由画布，拖拽节点与正交连线，保存为标准 DefJson。
          </p>
        </div>

        <div className="mt-auto border-t border-border p-3">
          <UserSwitcher />
        </div>
      </aside>

      <div className="flex min-h-screen w-full flex-col lg:pl-[248px]">
        <MobileBar pending={pending} />
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}

function MobileBar({ pending }: { pending: number }) {
  const pathname = stripBasePath(usePathname());
  return (
    <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-card/90 px-4 py-3 backdrop-blur-xl lg:hidden">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#3f7bff] to-[#1f4fd8] text-white">
        <Workflow className="h-4 w-4" />
      </div>
      <span className="mr-auto text-sm font-semibold">Flow Studio</span>
      {NAV.map((item) => {
        const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "relative rounded-md px-2 py-1 text-xs",
              active ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground",
            )}
          >
            {item.label}
            {item.badge === "tasks" && pending > 0 && (
              <span className="absolute -right-1 -top-1 h-1.5 w-1.5 rounded-full bg-primary" />
            )}
          </Link>
        );
      })}
    </div>
  );
}

function UserSwitcher() {
  const { user, users, canSwitch, switchUser } = useSession();

  const identity = (
    <>
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-900 text-[11px] font-semibold text-white">
        {initials(user.name)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-medium">{user.name}</span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {user.group} · {user.roles?.[0] || "employee"}
        </span>
      </span>
    </>
  );

  if (!canSwitch) {
    return <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">{identity}</div>;
  }

  return (
    <details className="group relative">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 rounded-lg px-2 py-2 transition hover:bg-accent [&::-webkit-details-marker]:hidden">
        {identity}
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground transition group-open:rotate-180" />
      </summary>
      <div className="absolute bottom-[calc(100%+8px)] left-0 z-40 w-full min-w-[210px] overflow-hidden rounded-xl border border-border bg-card p-1.5 shadow-[0_18px_50px_rgba(16,24,40,0.18)]">
        <p className="px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          切换演示身份
        </p>
        {users.map((item) => (
          <button
            key={item.handler}
            type="button"
            onClick={() => switchUser(item.handler)}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left transition hover:bg-accent"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground">
              {initials(item.name)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium">{item.name}</span>
              <span className="block truncate text-[10px] text-muted-foreground">{item.group}</span>
            </span>
            {item.handler === user.handler && <Check className="h-3.5 w-3.5 text-primary" />}
          </button>
        ))}
      </div>
    </details>
  );
}
