"use client";

import { Suspense } from "react";

import { ShellLayout } from "@/extensions/shell";
import { WorkspaceHome } from "@/extensions/workspace/WorkspaceHome";

export default function CollabWorkspacePage() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            加载中...
          </div>
        }
      >
        <WorkspaceHome />
      </Suspense>
    </ShellLayout>
  );
}
