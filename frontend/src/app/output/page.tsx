"use client";

import { Suspense } from "react";

import { ShellLayout } from "@/extensions/shell";
import { Toaster } from "@/components/ui/sonner";
import { OutputManager } from "@/extensions/output/OutputManager";

function OutputLayoutFallback({ children }: { children: React.ReactNode }) {
  return (
    <ShellLayout>
      <div className="flex flex-col h-full bg-muted">
        <header className="bg-background border-b border-border h-15 flex items-center px-6 shrink-0">
          <span className="font-bold text-lg tracking-tight text-foreground mr-8">报告输出</span>
        </header>
        <div className="flex-1 overflow-hidden min-w-0 min-h-0 bg-background">{children}</div>
      </div>
    </ShellLayout>
  );
}

export default function OutputPage() {
  return (
    <>
      <Suspense
        fallback={
          <OutputLayoutFallback>
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              加载中...
            </div>
          </OutputLayoutFallback>
        }
      >
        <OutputManager />
      </Suspense>
      <Toaster />
    </>
  );
}
