"use client";

import { Blocks } from "lucide-react";
import { useCallback, useState } from "react";

import { AppManagement } from "./AppManagement";
import { DomainManagement } from "./DomainManagement";

export default function AdminAppCenterPage() {
  // ponytail: refreshKey lets DomainManagement notify AppManagement to re-fetch domains
  const [refreshKey, setRefreshKey] = useState(0);
  const notifyDomainsChanged = useCallback(
    () => setRefreshKey((k) => k + 1),
    [],
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <header className="mb-8 flex items-start gap-3">
          <div className="border-primary/20 bg-primary/10 text-primary shrink-0 rounded-lg border p-3">
            <Blocks className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-foreground text-2xl font-bold tracking-tight">
              应用管理
            </h1>
            <p className="text-muted-foreground mt-1 text-sm">
              管理应用中心的业务域分类与应用条目，修改即时生效。
            </p>
          </div>
        </header>

        <div className="space-y-10">
          <DomainManagement onDomainsChanged={notifyDomainsChanged} />
          <AppManagement refreshKey={refreshKey} />
        </div>
      </div>
    </div>
  );
}
