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
      <Suspense
        fallback={
          <div
            className="flex h-full items-center justify-center"
            style={{ background: "var(--cyber-bg-primary, #020617)" }}
          >
            <span className="font-cyber text-xs tracking-widest text-[var(--cyber-text-muted)] uppercase">
              &gt; LOADING PROJECT DATA...
            </span>
          </div>
        }
      >
        <SciFiProjectDetail projectId={id} />
      </Suspense>
    </ShellLayout>
  );
}
