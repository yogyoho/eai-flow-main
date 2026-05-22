"use client";

import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import PluginMarketplace from "@/extensions/plugin/PluginMarketplace";
import { ShellLayout } from "@/extensions/shell";

export default function PluginsPage() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            加载中...
          </div>
        }
      >
        <PluginMarketplace />
      </Suspense>
      <Toaster />
    </ShellLayout>
  );
}
