"use client";

import { useMyTasks } from "../hooks/useMyTasks";
import { TaskItemCard } from "./TaskItemCard";

export function TodayTasks() {
  const { data, isLoading } = useMyTasks();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} />
        ))}
      </div>
    );
  }

  if (!data || data.tasks.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p>没有待办任务</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {data.urgent_count > 0 && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-red-500 font-semibold text-sm">
            紧急 ({data.urgent_count})
          </span>
        </div>
      )}
      {data.tasks.map((task) => (
        <TaskItemCard key={task.id} task={task} />
      ))}
    </div>
  );
}

function Skeleton() {
  return <div className="h-14 rounded-lg bg-muted animate-pulse" />;
}
