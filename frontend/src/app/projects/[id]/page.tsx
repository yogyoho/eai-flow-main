"use client";

import { Suspense, use } from "react";

import { ShellLayout } from "@/extensions/shell";
import { ProjectDetail } from "@/extensions/project/ProjectDetail";

export default function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            加载中...
          </div>
        }
      >
        <ProjectDetail projectId={id} />
      </Suspense>
    </ShellLayout>
  );
}
