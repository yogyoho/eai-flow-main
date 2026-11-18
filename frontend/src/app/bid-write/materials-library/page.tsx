"use client";

// EAI-CUSTOM 批卅二——素材库独立页(六类素材实体,owner 级资产;设计
// docs/superpowers/specs/2026-11-18-bid-write-materials-library-design.md)。
import { Suspense } from "react";

import { LibraryView } from "@/extensions/bid-write/components/LibraryView";

export default function MaterialsLibraryRoute() {
  return (
    <Suspense
      fallback={<div className="bw-muted bw-p">加载中…</div>}
    >
      <LibraryView />
    </Suspense>
  );
}
