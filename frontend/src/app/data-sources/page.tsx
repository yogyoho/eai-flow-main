"use client";

import { Suspense } from "react";

import { DataSourceManager } from "@/extensions/data-source/DataSourceManager";
import { ShellLayout } from "@/extensions/shell";
import { Loader2 } from "lucide-react";

export default function DataSourcesPage() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            <Loader2 className="h-8 w-8 animate-spin text-primary mr-2" />
            加载中...
          </div>
        }
      >
        <DataSourceManager />
      </Suspense>
    </ShellLayout>
  );
}
