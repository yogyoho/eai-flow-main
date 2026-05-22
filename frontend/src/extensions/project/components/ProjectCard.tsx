"use client";

import { motion } from "framer-motion";
import { Edit, Trash2 } from "lucide-react";
import React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ReportProject } from "@/extensions/project/types";
import { REPORT_TYPE_LABELS } from "@/extensions/project/types";

import { StatusBadge } from "./StatusBadge";

interface ProjectCardProps {
  project: ReportProject;
  onClick: () => void;
  onEdit: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
}

const REPORT_TYPE_COLORS: Record<string, string> = {
  environmental_impact: "border-green-500/20 bg-green-500/10 text-green-600",
  geological_survey: "border-amber-500/20 bg-amber-500/10 text-amber-600",
  feasibility_study: "border-blue-500/20 bg-blue-500/10 text-blue-600",
  safety_assessment: "border-red-500/20 bg-red-500/10 text-red-600",
  energy_assessment: "border-purple-500/20 bg-purple-500/10 text-purple-600",
  other: "border-primary/20 bg-primary/10 text-primary",
};

const REPORT_TYPE_ICONS: Record<string, string> = {
  environmental_impact: "环",
  geological_survey: "地",
  feasibility_study: "可",
  safety_assessment: "安",
  energy_assessment: "节",
  other: "报",
};

const AVATAR_COLORS = [
  "bg-blue-500 text-white",
  "bg-green-500 text-white",
  "bg-amber-500 text-white",
  "bg-purple-500 text-white",
  "bg-pink-500 text-white",
  "bg-cyan-500 text-white",
];

function getInitials(name: string): string {
  if (!name) return "?";
  // For Chinese names, take the last 1-2 characters
  if (/[一-鿿]/.test(name)) {
    return name.slice(-2);
  }
  // For English names, take first letter of first and last name
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return ((parts[0]?.[0] ?? "") + (parts[parts.length - 1]?.[0] ?? "")).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function formatDate(dateString: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(dateString));
}

export function ProjectCard({ project, onClick, onEdit, onDelete }: ProjectCardProps) {
  const typeColor = REPORT_TYPE_COLORS[project.reportType] ?? REPORT_TYPE_COLORS.other;
  const typeIcon = REPORT_TYPE_ICONS[project.reportType] ?? REPORT_TYPE_ICONS.other;
  const typeLabel = REPORT_TYPE_LABELS[project.reportType] ?? project.reportType;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      onClick={onClick}
      className="group flex cursor-pointer flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm transition-all hover:shadow-md"
    >
      {/* Top section */}
      <div className="flex-1 p-5">
        <div className="mb-4 flex items-start gap-3">
          <div
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border text-sm font-bold",
              typeColor,
            )}
          >
            {typeIcon}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="line-clamp-1 font-semibold text-foreground">{project.name}</h3>
            <div className="mt-1">
              <StatusBadge status={project.status} type="project" />
            </div>
          </div>
        </div>

        {/* Middle: 3-column grid */}
        <div className="grid grid-cols-3 gap-3 border-t border-border py-3">
          <div>
            <div className="mb-1 text-xs text-muted-foreground">委托方</div>
            <div className="truncate text-sm font-medium text-foreground" title={project.client}>
              {project.client || "-"}
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs text-muted-foreground">报告类型</div>
            <div className="truncate text-sm font-medium text-foreground" title={typeLabel}>
              {typeLabel}
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs text-muted-foreground">创建日期</div>
            <div className="text-sm font-medium text-foreground">{formatDate(project.createdAt)}</div>
          </div>
        </div>
      </div>

      {/* Bottom: Member avatars + action buttons */}
      <div className="flex items-center justify-between border-t border-border bg-muted/50 px-5 py-3">
        <div className="flex items-center">
          {project.members.length === 0 ? (
            <span className="text-xs text-muted-foreground">暂无成员</span>
          ) : (
            <div className="flex -space-x-1.5">
              {project.members.slice(0, 4).map((member, idx) => (
                <div
                  key={member.userId}
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full border-2 border-background text-[9px] font-medium",
                    AVATAR_COLORS[idx % AVATAR_COLORS.length],
                  )}
                  title={`${member.username} (${member.role})`}
                >
                  {getInitials(member.username)}
                </div>
              ))}
              {project.members.length > 4 && (
                <div className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-background bg-muted text-[9px] font-medium text-muted-foreground">
                  +{project.members.length - 4}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <Button
            variant="ghost"
            size="icon"
            onClick={onEdit}
            className="h-7 w-7 text-muted-foreground hover:bg-muted hover:text-foreground"
            title="编辑"
          >
            <Edit className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onDelete}
            className="h-7 w-7 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            title="删除"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
