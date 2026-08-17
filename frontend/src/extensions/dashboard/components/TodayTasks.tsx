"use client";

import { CheckCircle2 } from "lucide-react";

import { useMyTasks } from "../hooks/useMyTasks";

import { TaskItemCard } from "./TaskItemCard";

export function TodayTasks() {
  const { data, isLoading } = useMyTasks();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="bg-muted h-14 animate-pulse rounded-lg" />
        ))}
      </div>
    );
  }

  // Empty state — no tasks at all
  if (!data || data.tasks.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-8">
        <CheckCircle2 className="h-8 w-8 text-green-500/60" />
        <p className="text-muted-foreground text-sm">所有任务已完成</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {data.tasks.map((task) => (
        <TaskItemCard key={task.id} task={task} />
      ))}
      {data.total_count > data.tasks.length && (
        <p className="text-muted-foreground pt-1 text-center text-xs">
          还有 {data.total_count - data.tasks.length} 项任务
        </p>
      )}
    </div>
  );
}
