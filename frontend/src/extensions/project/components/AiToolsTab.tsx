"use client";

import { AiToolbox } from "@/extensions/project/AiToolbox";
import { type ReportProject } from "@/extensions/project/types";

interface AiToolsTabProps {
  project: ReportProject;
  onRefresh: () => void;
  can?: (action: string) => boolean;
}

export function AiToolsTab({ project, onRefresh, can: _can }: AiToolsTabProps) {
  return <AiToolbox project={project} onRefresh={onRefresh} />;
}
