"use client";

import { Suspense } from "react";

import { ReviewView } from "@/extensions/bid-write/components/ReviewView";

export default function BidWriteReviewPage() {
  return (
    <Suspense fallback={<div className="bw-page-loading">加载中…</div>}>
      <ReviewView />
    </Suspense>
  );
}
