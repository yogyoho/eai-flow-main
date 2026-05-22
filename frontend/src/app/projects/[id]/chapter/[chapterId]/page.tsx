"use client";

import { use } from "react";

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
      <ChapterEditor projectId={id} chapterId={chapterId} />
    </ShellLayout>
  );
}
