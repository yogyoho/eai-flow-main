"use client";

// Collab Workspace Tier 1 — 快速文档编辑器（复用 CollabEditor + AI menu）
// EAI-CUSTOM: 全新模块

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import "@/extensions/dashboard/dashboard.css";
import { CollabEditor } from "@/extensions/collab/CollabEditor";
import type { CollabProject } from "../types";

interface QuickDocEditorProps {
  project: CollabProject;
  onRefresh: () => void;
}

export function QuickDocEditor({ project, onRefresh }: QuickDocEditorProps) {
  const [docId, setDocId] = useState<string | null>(null);

  useEffect(() => {
    setDocId(project.docId);
  }, [project.docId]);

  if (!docId) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {project.kind === "quickdoc" ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : "该文档在「文档」标签编辑"}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col" style={{ minHeight: 0 }}>
      <div className="px-4 py-2 flex items-center justify-between border-b" style={{ borderColor: "var(--db-border)" }}>
        <span className="text-xs font-mono text-muted-foreground">
          {project.name} · 快速文档（AI 起草 + 修订模式）
        </span>
      </div>
      <div className="flex-1 overflow-auto" style={{ minHeight: 0 }}>
        <CollabEditor documentId={docId} projectId={project.id} />
      </div>
    </div>
  );
}
