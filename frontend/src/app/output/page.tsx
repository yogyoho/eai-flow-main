"use client";

import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { OutputManager } from "@/extensions/output/OutputManager";
import { ShellLayout } from "@/extensions/shell";

export default function OutputPage() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            加载中...
          </div>
        }
      >
        <OutputManager />
      </Suspense>
      <Toaster />
    </ShellLayout>
  );
}
