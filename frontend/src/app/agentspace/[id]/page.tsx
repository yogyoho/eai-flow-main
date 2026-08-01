"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { ProjectDetail } from "@/extensions/workspace/ProjectDetail";
import { ShellLayout } from "@/extensions/shell";

export default function CollabProjectPage() {
  const params = useParams<{ id: string }>();
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">加载中...</div>
        }
      >
        <ProjectDetail projectId={params.id} />
      </Suspense>
    </ShellLayout>
  );
}
