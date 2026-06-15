"use client";

import { Suspense } from "react";

import { AppCenterPage } from "@/extensions/app-center";
import { ShellLayout } from "@/extensions/shell";

export default function AppCenterRoute() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            加载中...
          </div>
        }
      >
        <AppCenterPage />
      </Suspense>
    </ShellLayout>
  );
}
