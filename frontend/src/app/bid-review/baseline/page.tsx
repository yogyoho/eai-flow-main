"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { BaselineView } from "@/extensions/bid-review/components/BaselineView";

function BaselineContent() {
  const params = useSearchParams();
  return <BaselineView taskId={params.get("task_id")} />;
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
