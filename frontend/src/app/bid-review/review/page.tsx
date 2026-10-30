"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { ReviewQueueView } from "@/extensions/bid-review/components/ReviewQueueView";

function ReviewContent() {
  const params = useSearchParams();
  return <ReviewQueueView taskId={params.get("task_id")} />;
}

export default function BidReviewReviewPage() {
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
        <ReviewContent />
      </Suspense>
    </>
  );
}
