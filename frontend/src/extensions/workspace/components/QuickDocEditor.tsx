"use client";

// Collab Workspace Tier 1 — 快速文档编辑器（复用 CollabEditor + AI menu）
// EAI-CUSTOM: 全新模块。UI 对齐 cyber 主题。

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { CollabEditor } from "@/extensions/collab/CollabEditor";

import type { CollabProject } from "../types";

interface QuickDocEditorProps {
  project: CollabProject;
  onRefresh: () => void;
}

export function QuickDocEditor({ project }: QuickDocEditorProps) {
  const [docId, setDocId] = useState<string | null>(null);

  useEffect(() => {
    setDocId(project.docId);
  }, [project.docId]);

  if (!docId) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        {project.kind === "quickdoc" ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          "该文档在「文档」标签编辑"
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col" style={{ minHeight: 0 }}>
      <div
        className="flex items-center justify-between border-b px-4 py-2"
        style={{ borderColor: "var(--cyber-border-muted)" }}
      >
        <span className="text-muted-foreground font-mono text-xs">
          {project.name} · 快速文档（AI 起草 + 修订模式）
        </span>
      </div>
      <div className="flex-1 overflow-auto" style={{ minHeight: 0 }}>
        <CollabEditor documentId={docId} projectId={project.id} />
      </div>
    </div>
  );
}
