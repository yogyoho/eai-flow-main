"use client";

import { Loader2 } from "lucide-react";
import { Suspense } from "react";

import { DataSourceManager } from "@/extensions/data-source/DataSourceManager";
import { ShellLayout } from "@/extensions/shell";

export default function DataSourcesPage() {
  return (
    <ShellLayout>
      <Suspense
        fallback={
          <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
            <Loader2 className="text-primary mr-2 h-8 w-8 animate-spin" />
            加载中...
          </div>
        }
      >
        <DataSourceManager />
      </Suspense>
    </ShellLayout>
  );
}
