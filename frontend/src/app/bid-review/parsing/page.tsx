"use client";

import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { ParsingView } from "@/extensions/bid-review/components/ParsingView";
import { useSelectedTask } from "@/extensions/bid-review/hooks";

// UX 重构 Plan6 (spec §4.3):解析与字段抽取归拢专屏(原型 s3)。
function ParsingContent() {
  // 选中任务模型(spec §3.2,Plan2):URL param → 最新任务 fallback;null 仅当零任务
  const { taskId } = useSelectedTask();
  return <ParsingView taskId={taskId} />;
}

export default function BidReviewParsingPage() {
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
        <ParsingContent />
      </Suspense>
    </>
  );
}
