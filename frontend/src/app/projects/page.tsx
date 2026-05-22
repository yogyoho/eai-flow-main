"use client";

import { Suspense } from "react";

import { ProjectList } from "@/extensions/project/ProjectList";
import { ShellLayout } from "@/extensions/shell";

export default function ProjectsPage() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">加载中...</div>
        }
      >
        <ProjectList />
      </Suspense>
    </ShellLayout>
  );
}
