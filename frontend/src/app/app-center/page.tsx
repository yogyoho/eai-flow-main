"use client";

import { Suspense } from "react";

import { AppCenterPage } from "@/extensions/app-center";
import { ShellLayout } from "@/extensions/shell";

export default function AppCenterRoute() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            加载中...
          </div>
        }
      >
        <AppCenterPage />
      </Suspense>
    </ShellLayout>
  );
}
