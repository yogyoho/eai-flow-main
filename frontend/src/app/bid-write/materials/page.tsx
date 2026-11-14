"use client";

import { Suspense } from "react";

import { MaterialsView } from "@/extensions/bid-write/components/MaterialsView";

export default function BidWriteMaterialsPage() {
  return (
    <Suspense fallback={<div className="bw-page-loading">加载中…</div>}>
      <MaterialsView />
    </Suspense>
  );
}
