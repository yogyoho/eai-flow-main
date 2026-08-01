"use client";

import { Suspense } from "react";

import { WorkspaceHome } from "@/extensions/workspace/WorkspaceHome";
import { ShellLayout } from "@/extensions/shell";

export default function CollabWorkspacePage() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">加载中...</div>
        }
      >
        <WorkspaceHome />
      </Suspense>
    </ShellLayout>
  );
}
