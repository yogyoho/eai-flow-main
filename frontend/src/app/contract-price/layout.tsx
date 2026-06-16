"use client";

import {
  LayoutDashboard,
  FileText,
  Boxes,
  ListChecks,
  History,
  Settings,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ShellLayout } from "@/extensions/shell";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/contract-price", label: "总览", icon: LayoutDashboard, exact: true },
  { href: "/contract-price/contracts", label: "合同清单", icon: FileText },
  { href: "/contract-price/clusters", label: "聚类审核", icon: Boxes },
  { href: "/contract-price/items", label: "分项明细", icon: ListChecks },
  { href: "/contract-price/tasks", label: "任务历史", icon: History },
  { href: "/contract-price/settings", label: "配置", icon: Settings },
];

function ContractPriceLayoutContent({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="flex h-16 shrink-0 items-center border-b border-border bg-background px-6">
        <span className="mr-8 text-lg font-bold tracking-tight text-foreground">
          合同价格分析
        </span>
        <nav className="flex h-full items-center gap-6 text-sm font-medium text-muted-foreground">
          {navItems.map(({ href, label, icon: Icon, exact }) => {
            const isActive = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex h-full items-center gap-1.5 border-b-2 py-5 transition-colors",
                  isActive
                    ? "border-primary text-primary"
                    : "border-transparent hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </header>
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}

export default function ContractPriceLayout({ children }: { children: ReactNode }) {
  return (
    <ShellLayout>
      <ContractPriceLayoutContent>{children}</ContractPriceLayoutContent>
    </ShellLayout>
  );
}
