"use client";

import { Suspense } from "react";

import { ShellLayout } from "@/extensions/shell";
import PluginMarketplace from "@/extensions/plugin/PluginMarketplace";
import { Toaster } from "@/components/ui/sonner";

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
