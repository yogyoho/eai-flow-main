"use client";

import { Blocks } from "lucide-react";

import { AppManagement } from "./AppManagement";
import { DomainManagement } from "./DomainManagement";

export default function AdminAppCenterPage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="mb-8 flex items-start gap-3">
          <div className="p-3 border rounded-lg bg-blue-50 border-blue-200 text-blue-600 shrink-0">
            <Blocks className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              应用管理
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              管理应用中心的业务域分类与应用条目，修改即时生效。
            </p>
          </div>
        </header>

        <div className="space-y-10">
          <DomainManagement />
          <AppManagement />
        </div>
      </div>
    </div>
  );
}
