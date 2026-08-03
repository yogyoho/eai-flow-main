"use client";

import { QueryClientProvider } from "@/components/query-client-provider";
import { AuthProvider } from "@/extensions/hooks/useAuth";
import { PermissionProvider } from "@/core/permissions";

import { ExtensionsSidebar } from "./Sidebar";

export function ShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider>
      <AuthProvider>
        <PermissionProvider>
          {/* EAI-CUSTOM: fixed inset-0 替代 h-screen —— 脱离文档流隔离内部滚动，
              否则内层 overflow-y-auto 内容会把 documentElement.scrollHeight 撑大，
              产生页面级滚动条并把面板内容顶出视口（角色管理 tab 下部大片留白） */}
          <div className="flex fixed inset-0 overflow-hidden bg-background dark:bg-background">
            <ExtensionsSidebar />
            <div className="flex-1 flex flex-col overflow-hidden min-w-0">
              <main className="flex-1 min-h-0 overflow-y-auto">{children}</main>
            </div>
          </div>
        </PermissionProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
