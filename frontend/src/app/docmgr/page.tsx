"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
import DocumentManagement from "@/extensions/docmgr/DocumentManagement";

function DocMgrContent() {
  const params = useSearchParams();
  const openDocId = params.get("open") ?? undefined;
  return <DocumentManagement initialDocId={openDocId} />;
}

export default function DocMgrPage() {
  return (
    <SimpleShellLayout>
      <Suspense fallback={<div className="flex items-center justify-center h-full text-muted-foreground text-sm">加载中...</div>}>
        <DocMgrContent />
      </Suspense>
    </SimpleShellLayout>
  );
}
