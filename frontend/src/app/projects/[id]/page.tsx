"use client";

import { Suspense, use } from "react";

import { ProjectDetail } from "@/extensions/project/ProjectDetail";
import { ShellLayout } from "@/extensions/shell";

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
