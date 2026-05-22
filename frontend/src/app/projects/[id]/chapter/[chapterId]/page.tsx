"use client";

import { Suspense, use } from "react";

import { ChapterEditor } from "@/extensions/project/ChapterEditor";
import { ShellLayout } from "@/extensions/shell";

export default function ChapterEditorPage({
  params,
}: {
  params: Promise<{ id: string; chapterId: string }>;
}) {
  const { id, chapterId } = use(params);
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            加载中...
          </div>
        }
      >
        <ChapterEditor projectId={id} chapterId={chapterId} />
      </Suspense>
    </ShellLayout>
  );
}
