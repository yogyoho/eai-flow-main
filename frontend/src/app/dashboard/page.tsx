"use client";

import { Suspense } from "react";

import { DashboardPage } from "@/extensions/dashboard/DashboardPage";
import { ShellLayout } from "@/extensions/shell";

export default function DashboardRoute() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            加载中...
          </div>
        }
      >
        <DashboardPage />
      </Suspense>
    </ShellLayout>
  );
}
