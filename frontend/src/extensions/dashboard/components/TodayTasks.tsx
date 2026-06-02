"use client";

import { Inbox } from "lucide-react";
import { useMyTasks } from "../hooks/useMyTasks";
import { TaskItemCard } from "./TaskItemCard";

export function TodayTasks() {
  const { data, isLoading } = useMyTasks();

  if (isLoading) {
    return (
      <div className="rounded-xl border bg-card shadow-sm p-5 space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} />
        ))}
      </div>
    );
  }

  if (!data || data.tasks.length === 0) {
    return (
      <div className="rounded-xl border bg-card shadow-sm">
        <div className="px-5 pt-5 pb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">今日待办</h2>
        </div>
        <div className="py-10 flex flex-col items-center gap-2">
          <Inbox className="h-10 w-10 text-muted-foreground/50" />
          <p className="text-sm text-muted-foreground">暂无待办任务</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-card shadow-sm">
      <div className="px-5 pt-5 pb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold">今日待办</h2>
        {data.urgent_count > 0 && (
          <span className="bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded-full font-medium">
            紧急 {data.urgent_count}
          </span>
        )}
      </div>
      <div className="space-y-2 px-5 pb-5">
        {data.tasks.map((task) => (
          <TaskItemCard key={task.id} task={task} />
        ))}
      </div>
    </div>
  );
}

function Skeleton() {
  return <div className="h-14 rounded-lg bg-muted animate-pulse" />;
}
