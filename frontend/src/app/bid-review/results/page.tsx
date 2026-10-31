"use client";

import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { ResultsView } from "@/extensions/bid-review/components/ResultsView";
import { useSelectedTask } from "@/extensions/bid-review/hooks";

// UX 重构 Plan7 (spec §4.5,裁定8):审查结果专屏(原型 s5),自 WorkbenchView 拆分。
function ResultsContent() {
  // 选中任务模型(spec §3.2,Plan2):URL param → 最新任务 fallback;null 仅当零任务
  const { taskId } = useSelectedTask();
  return <ResultsView taskId={taskId} />;
}

export default function BidReviewResultsPage() {
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
        <ResultsContent />
      </Suspense>
    </>
  );
}
