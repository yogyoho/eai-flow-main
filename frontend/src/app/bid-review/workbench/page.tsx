"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Toaster } from "@/components/ui/sonner";
import { WorkbenchView } from "@/extensions/bid-review/components/WorkbenchView";

function WorkbenchContent() {
  const params = useSearchParams();
  return <WorkbenchView taskId={params.get("task_id")} />;
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
