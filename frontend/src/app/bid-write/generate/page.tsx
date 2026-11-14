"use client";

import { Suspense } from "react";

import { GenerateView } from "@/extensions/bid-write/components/GenerateView";

export default function BidWriteGeneratePage() {
  return (
    <Suspense fallback={<div className="bw-page-loading">加载中…</div>}>
      <GenerateView />
    </Suspense>
  );
}
