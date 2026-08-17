"use client";

import {
  BookOpen,
  ChevronsUpDown,
  Factory,
  LogOut,
  SettingsIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
// EAI-CUSTOM: nav-level permission gating
import { usePermission } from "@/core/permissions";

import { SettingsDialog } from "./settings";

function NavMenuButtonContent({ isSidebarOpen }: { isSidebarOpen: boolean }) {
  return isSidebarOpen ? (
    <div className="text-muted-foreground flex w-full items-center gap-2 text-left text-sm">
      <SettingsIcon className="size-4" />
      <span>设置和更多</span>
      <ChevronsUpDown className="text-muted-foreground ml-auto size-4" />
    </div>
  ) : (
    <div className="flex size-full items-center justify-center">
      <SettingsIcon className="text-muted-foreground size-4" />
    </div>
  );
}

export function WorkspaceNavMenu() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const { open: isSidebarOpen } = useSidebar();
  const router = useRouter();
  const { canNav } = usePermission();

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleLogout = async () => {
    try {
      await fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // best-effort
    }
    window.location.href = "/";
  };

  return (
    <>
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
      <SidebarMenu className="w-full">
        <SidebarMenuItem>
          {mounted ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <NavMenuButtonContent isSidebarOpen={isSidebarOpen} />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
                align="end"
                sideOffset={4}
              >
                <DropdownMenuGroup>
                  {canNav("nav:settings") && (
                    <DropdownMenuItem onClick={() => setSettingsOpen(true)}>
                      <SettingsIcon className="size-4" />
                      设置
                    </DropdownMenuItem>
                  )}
                  {canNav("nav:knowledge") && (
                    <DropdownMenuItem onClick={() => router.push("/knowledge")}>
                      <BookOpen className="size-4" />
                      知识库
                    </DropdownMenuItem>
                  )}
                  {canNav("nav:knowledge-factory") && (
                    <DropdownMenuItem
                      onClick={() => router.push("/knowledge-factory")}
                    >
                      <Factory className="size-4" />
                      知识工厂
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout}>
                    <LogOut className="size-4" />
                    退出登录
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <SidebarMenuButton size="lg" className="pointer-events-none">
              <NavMenuButtonContent isSidebarOpen={isSidebarOpen} />
            </SidebarMenuButton>
          )}
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}
