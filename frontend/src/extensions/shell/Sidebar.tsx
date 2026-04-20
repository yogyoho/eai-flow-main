"use client";

import {
  Bot,
  Factory,
  BookOpen,
  Settings2,
  LogOut,
  UserCircle,
  User,
  FolderCheck,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { useAuth } from "@/extensions/hooks/useAuth";
import { cn } from "@/lib/utils";

const navItems: { href: string; label: string; icon: React.ElementType }[] = [
  { href: "/writing", label: "智能写作", icon: Bot },
  { href: "/docmgr", label: "文档空间", icon: FolderCheck },
  { href: "/knowledge-factory", label: "知识工厂", icon: Factory },
  { href: "/knowledge", label: "知识库", icon: BookOpen },
  { href: "/admin", label: "系统管理", icon: Settings2 },
];

function NavIcon({
  href,
  label,
  icon: Icon,
  isActive,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  isActive: boolean;
}) {
  return (
    <Tooltip delayDuration={300}>
      <TooltipTrigger asChild>
        <Link
          href={href}
          className={cn(
            "flex items-center justify-center w-10 h-10 rounded-lg transition-colors",
            isActive
              ? "text-primary bg-primary/10"
              : "text-muted-foreground hover:text-primary hover:bg-accent"
          )}
        >
          <Icon className="h-5 w-5" />
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

export function ExtensionsSidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleLogout = () => {
    logout();
  };

  return (
    <TooltipProvider delayDuration={300}>
      <div className="relative z-30 w-14 shrink-0 flex flex-col items-center border-r border-border bg-background dark:bg-zinc-900">
        {/* Logo */}
        <div className="p-3 border-b border-border">
          <Link
            href="/"
            className="w-9 h-9 rounded-lg flex items-center justify-center hover:bg-accent transition-colors"
          >
            <img src="/favicon.svg" alt="Logo" className="w-7 h-7" />
          </Link>
        </div>

        {/* Main navigation */}
        <nav className="flex-1 flex flex-col items-center py-4 gap-4">
          {navItems.map(({ href, label, icon }) => {
            const isActive =
              pathname === href ||
              (href === "/admin" && pathname.startsWith("/admin"));
            return (
              <NavIcon
                key={href}
                href={href}
                label={label}
                icon={icon}
                isActive={isActive}
              />
            );
          })}
        </nav>

        {/* User menu */}
        <div className="p-2 border-t border-border flex flex-col items-center gap-1">
          {mounted && (
            <DropdownMenu>
              <Tooltip delayDuration={300}>
                <TooltipTrigger asChild>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex items-center justify-center w-10 h-10 rounded-lg text-muted-foreground hover:text-primary hover:bg-accent transition-colors"
                    >
                      <User className="h-5 w-5" />
                    </button>
                  </DropdownMenuTrigger>
                </TooltipTrigger>
                <TooltipContent side="right" sideOffset={8}>
                  用户信息
                </TooltipContent>
              </Tooltip>
              <DropdownMenuContent side="right" sideOffset={8} className="w-48">
                <div className="px-2 py-2 border-b border-border">
                  <div className="text-sm font-medium text-foreground">
                    {user?.username ?? "—"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    ID: {user?.id ?? "—"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {user?.role_name ?? ""}
                  </div>
                </div>

                <DropdownMenuItem className="cursor-pointer">
                  <UserCircle className="mr-2 h-4 w-4" />
                  个人资料
                </DropdownMenuItem>

                <DropdownMenuSeparator />

                <DropdownMenuItem
                  className="cursor-pointer text-destructive focus:text-destructive"
                  onClick={handleLogout}
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  退出登录
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}
