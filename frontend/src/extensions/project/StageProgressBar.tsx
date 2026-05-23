"use client";

import { Check } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

import { STAGE_LABELS } from "./types";

const STAGE_ICONS = ["📋", "📝", "🤖", "👥", "✅", "📄"];

interface StageProgressBarProps {
  projectId: string;
  currentStage: number;
}

export function StageProgressBar({ projectId, currentStage }: StageProgressBarProps) {
  return (
    <div className="flex items-center gap-1 px-6">
      {STAGE_LABELS.map((label, index) => {
        const stage = index + 1;
        const isCompleted = stage < currentStage;
        const isCurrent = stage === currentStage;
        const isFuture = stage > currentStage;

        const href = `/projects/${projectId}?stage=${stage}`;

        return (
          <Link
            key={stage}
            href={isFuture ? "#" : href}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              isCompleted && "bg-primary/10 text-primary hover:bg-primary/20",
              isCurrent && "bg-primary text-primary-foreground",
              isFuture && "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            <span className="text-sm">{STAGE_ICONS[index]}</span>
            <span>{label}</span>
            {isCompleted && <Check className="h-3 w-3" />}
          </Link>
        );
      })}
    </div>
  );
}