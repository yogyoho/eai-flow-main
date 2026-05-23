import { Suspense } from "react";

import { ProjectWorkspace } from "@/extensions/project/ProjectWorkspace";
import { ShellLayout } from "@/extensions/shell";

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <ShellLayout>
      <Suspense fallback={<div className="flex items-center justify-center h-full">加载中...</div>}>
        <ProjectWorkspace projectId={id} />
      </Suspense>
    </ShellLayout>
  );
}
