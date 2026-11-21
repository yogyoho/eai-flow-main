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
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
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
