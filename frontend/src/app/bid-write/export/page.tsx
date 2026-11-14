"use client";

import { Suspense } from "react";

import { ExportView } from "@/extensions/bid-write/components/ExportView";

export default function BidWriteExportPage() {
  return (
    <Suspense fallback={<div className="bw-page-loading">加载中…</div>}>
      <ExportView />
    </Suspense>
  );
}
