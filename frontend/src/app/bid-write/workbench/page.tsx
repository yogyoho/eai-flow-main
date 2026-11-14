"use client";

import { Suspense } from "react";

import { WorkbenchView } from "@/extensions/bid-write/components/WorkbenchView";

export default function BidWriteWorkbenchPage() {
  return (
    <Suspense fallback={<div className="bw-page-loading">加载中…</div>}>
      <WorkbenchView />
    </Suspense>
  );
}
