"use client";

import { QueryClientProvider } from "@/components/query-client-provider";
import { AuthProvider } from "@/extensions/hooks/useAuth";

import { ExtensionsSidebar } from "./Sidebar";

export function ShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider>
      <AuthProvider>
        <div className="flex h-screen bg-background dark:bg-background">
          <ExtensionsSidebar />
          <div className="flex-1 flex flex-col overflow-hidden min-w-0">
            <main className="flex-1 overflow-y-auto">{children}</main>
          </div>
        </div>
      </AuthProvider>
    </QueryClientProvider>
  );
}
