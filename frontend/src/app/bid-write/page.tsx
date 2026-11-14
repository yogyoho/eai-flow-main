"use client";

import { Suspense } from "react";

import { ProjectsView } from "@/extensions/bid-write/components/ProjectsView";

export default function BidWriteProjectsPage() {
  return (
    <Suspense fallback={<div className="bw-page-loading">加载中…</div>}>
      <ProjectsView />
    </Suspense>
  );
}
