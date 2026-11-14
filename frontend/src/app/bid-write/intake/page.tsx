"use client";

import { Suspense } from "react";

import { IntakeView } from "@/extensions/bid-write/components/IntakeView";

export default function BidWriteIntakePage() {
  return (
    <Suspense fallback={<div className="bw-page-loading">加载中…</div>}>
      <IntakeView />
    </Suspense>
  );
}
