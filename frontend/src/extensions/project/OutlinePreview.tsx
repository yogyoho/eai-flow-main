"use client";

import { OutlineEditor } from "./OutlineEditor";
import type { ChapterTreeNode } from "./types";

interface OutlinePreviewProps {
  chapters: ChapterTreeNode[];
}

export function OutlinePreview({ chapters }: OutlinePreviewProps) {
  return <OutlineEditor chapters={chapters} onChange={() => {}} readOnly />;
}
