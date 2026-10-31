"use client";

import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { BaselineView } from "@/extensions/bid-review/components/BaselineView";
import { useSelectedTask } from "@/extensions/bid-review/hooks";

function BaselineContent() {
  // 选中任务模型(spec §3.2,Plan2):URL param → 最新任务 fallback;null 仅当零任务
  const { taskId } = useSelectedTask();
  return <BaselineView taskId={taskId} />;
}

export default function BidReviewBaselinePage() {
  return (
    <>
      <Toaster />
      <Suspense
        fallback={
          <div className="text-muted-foreground flex items-center justify-center p-6 text-sm">
            加载中...
          </div>
        }
      >
        <BaselineContent />
      </Suspense>
    </>
  );
}
