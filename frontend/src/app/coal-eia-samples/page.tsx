"use client";

// EAI-CUSTOM (2026-09 样例库迁出): 煤矿环评报告样例库——应用中心独立应用薄壳。
// 自 knowledge-factory 的 kf:page:samples tab 迁出（KF 是通用模块，领域样例库不得混入）；
// 后端 /api/extensions/eia-samples/*，页面权限键 ces:page:samples（config/permissions.yaml）。
import { Suspense } from "react";

import { SampleLibrary } from "@/extensions/eia-samples";
import { ShellLayout } from "@/extensions/shell";

export default function CoalEiaSamplesRoute() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            加载中...
          </div>
        }
      >
        <SampleLibrary />
      </Suspense>
    </ShellLayout>
  );
}
