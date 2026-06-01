"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useMyProjects } from "../hooks/useMyProjects";
import { ProjectMiniCard } from "./ProjectMiniCard";

const GROUP_LABELS: Record<string, string> = {
  owner: "我负责的项目",
  phase_lead: "作为阶段负责人",
  reviewer: "作为审核人",
  writer: "作为撰写人",
  viewer: "仅查看",
};

export function MyProjects() {
  const { data, isLoading } = useMyProjects();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-20 rounded-lg bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  if (!data || data.total_count === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-4">暂无项目</p>
    );
  }

  const toggleGroup = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="space-y-3">
      {Object.entries(data.groups).map(([key, projects]) => (
        <div key={key}>
          <button
            onClick={() => toggleGroup(key)}
            className="flex items-center gap-1 text-sm font-medium mb-1 hover:text-primary"
          >
            {collapsed.has(key) ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
            {GROUP_LABELS[key] || key} ({projects.length})
          </button>
          {!collapsed.has(key) && (
            <div className="space-y-2 ml-2">
              {projects.map((p) => (
                <ProjectMiniCard key={p.project_id} project={p} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
