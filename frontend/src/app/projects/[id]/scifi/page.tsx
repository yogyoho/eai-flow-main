import { Suspense } from "react";

import { SciFiProjectDetail } from "@/extensions/project/SciFiProjectDetail";
import { ShellLayout } from "@/extensions/shell";

export default async function SciFiProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <ShellLayout>
      <Suspense fallback={
        <div className="flex items-center justify-center h-full" style={{ background: "var(--cyber-bg-primary, #020617)" }}>
          <span className="font-cyber text-xs text-[var(--cyber-text-muted)] tracking-widest uppercase">
            &gt; LOADING PROJECT DATA...
          </span>
        </div>
      }>
        <SciFiProjectDetail projectId={id} />
      </Suspense>
    </ShellLayout>
  );
}
