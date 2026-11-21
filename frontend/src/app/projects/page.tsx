"use client";

import { Suspense } from "react";

import { ProjectList } from "@/extensions/project/ProjectList";
import { ShellLayout } from "@/extensions/shell";

export default function ProjectsPage() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            加载中...
          </div>
        }
      >
        <ProjectList />
      </Suspense>
    </ShellLayout>
  );
}
