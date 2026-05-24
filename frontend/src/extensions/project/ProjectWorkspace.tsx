"use client";

import { ArrowLeft, ArrowRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { projectApi } from "@/extensions/project/api";
import { ChapterWritingPanel } from "@/extensions/project/ChapterWritingPanel";
import { OutlineEditor } from "@/extensions/project/OutlineEditor";
import { OutlinePreview } from "@/extensions/project/OutlinePreview";
import { SplitScreenLayout } from "@/extensions/project/SplitScreenLayout";
import { StageProgressBar } from "@/extensions/project/StageProgressBar";
import {
  STAGE_LABELS,
  type ChapterTreeNode,
  type ReportProject,
} from "@/extensions/project/types";
import { toast } from "sonner";

function chaptersToTreeNodes(chapters: ReportProject["chapters"]): ChapterTreeNode[] {
  return chapters.map((c) => ({
    id: c.id,
    title: c.title,
    level: c.level,
    sortOrder: c.sortOrder,
    purpose: c.purpose,
    generationHint: c.generationHint,
    wordCountTarget: c.wordCountTarget,
    children: chaptersToTreeNodes(c.children),
  }));
}

interface ProjectWorkspaceProps {
  projectId: string;
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const router = useRouter();
  const params = useSearchParams();
  const [project, setProject] = useState<ReportProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [outlineDraft, setOutlineDraft] = useState<ChapterTreeNode[]>([]);
  const [saving, setSaving] = useState(false);

  const currentStage = project?.currentStage ?? 1;
  const viewingStage = Number(params.get("stage")) || currentStage;

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectApi.get(projectId);
      setProject(data);
      if (data.chapters.length > 0) {
        setOutlineDraft(chaptersToTreeNodes(data.chapters));
      }
      // Setup-stage projects are created from the list dialog — redirect to outline
      if (data.status === "setup") {
        router.replace(`/projects/${projectId}?stage=2`);
      }
    } catch {
      toast.error("加载项目失败");
    } finally {
      setLoading(false);
    }
  }, [projectId, router]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  const handleSaveOutline = useCallback(async () => {
    if (!project) return;
    setSaving(true);
    try {
      const chapters = await projectApi.replaceOutline(project.id, outlineDraft);
      setProject((prev) => (prev ? { ...prev, chapters } : prev));
      toast.success("大纲已保存");
    } catch {
      toast.error("保存大纲失败");
    } finally {
      setSaving(false);
    }
  }, [project, outlineDraft]);

  const handleConfirmOutline = useCallback(async () => {
    if (!project) return;
    setSaving(true);
    try {
      await projectApi.replaceOutline(project.id, outlineDraft);
      const updated = await projectApi.confirmOutline(project.id);
      setProject(updated);
      toast.success("大纲已确认，进入AI撰写阶段");
      router.push(`/projects/${project.id}?stage=3`);
    } catch {
      toast.error("确认大纲失败");
    } finally {
      setSaving(false);
    }
  }, [project, outlineDraft, router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-sm text-destructive">项目不存在</p>
        <Link href="/projects">
          <Button variant="outline" size="sm">返回项目列表</Button>
        </Link>
      </div>
    );
  }

  // Stage 2: Outline Confirmation
  if (viewingStage === 2) {
    return (
      <div className="flex flex-col h-full">
        {/* Header */}
        <header className="bg-background border-b border-border px-6 py-3 flex items-center gap-4 shrink-0">
          <Link href="/projects">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="font-bold text-lg text-foreground">{project.name}</h1>
          <StageProgressBar projectId={projectId} currentStage={currentStage} />
          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleSaveOutline} disabled={saving}>
              {saving && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
              保存大纲
            </Button>
            <Button size="sm" onClick={handleConfirmOutline} disabled={saving}>
              确认大纲并进入撰写
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </header>

        {/* Split screen: editor + preview */}
        <SplitScreenLayout
          left={<OutlineEditor chapters={outlineDraft} onChange={setOutlineDraft} />}
          right={
            <div className="p-6">
              <h2 className="text-lg font-bold text-foreground mb-4">大纲预览</h2>
              <OutlinePreview chapters={outlineDraft} />
            </div>
          }
        />
      </div>
    );
  }

  // Stage 3: AI Writing
  if (viewingStage === 3) {
    return (
      <div className="flex flex-col h-full">
        <header className="bg-background border-b border-border px-6 py-3 flex items-center gap-4 shrink-0">
          <Link href="/projects">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="font-bold text-lg text-foreground">{project.name}</h1>
          <StageProgressBar projectId={projectId} currentStage={currentStage} />
        </header>
        <ChapterWritingPanel
          projectId={projectId}
          projectName={project.name}
          chapters={project.chapters}
        />
      </div>
    );
  }

  // Stages 4-6: Placeholder
  return (
    <div className="flex flex-col h-full">
      <header className="bg-background border-b border-border px-6 py-3 flex items-center gap-4 shrink-0">
        <Link href="/projects">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="font-bold text-lg text-foreground">{project.name}</h1>
        <StageProgressBar projectId={projectId} currentStage={currentStage} />
      </header>
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted-foreground text-sm">
          {STAGE_LABELS[viewingStage - 1]} 阶段开发中...
        </p>
      </div>
    </div>
  );
}
