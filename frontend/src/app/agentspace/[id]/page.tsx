"use client";

import { useParams } from "next/navigation";
import { Suspense } from "react";

import { ShellLayout } from "@/extensions/shell";
import { ProjectDetail } from "@/extensions/workspace/ProjectDetail";

export default function CollabProjectPage() {
  const params = useParams<{ id: string }>();
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            加载中...
          </div>
        }
      >
        <ProjectDetail projectId={params.id} />
      </Suspense>
    </ShellLayout>
  );
}
