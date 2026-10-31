"use client";

import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { WorkbenchView } from "@/extensions/bid-review/components/WorkbenchView";
import { useSelectedTask } from "@/extensions/bid-review/hooks";

function WorkbenchContent() {
  // 选中任务模型(spec §3.2,Plan2):URL param → 最新任务 fallback;null 仅当零任务
  const { taskId } = useSelectedTask();
  return <WorkbenchView taskId={taskId} />;
}

export default function BidReviewWorkbenchPage() {
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
        <WorkbenchContent />
      </Suspense>
    </>
  );
}
