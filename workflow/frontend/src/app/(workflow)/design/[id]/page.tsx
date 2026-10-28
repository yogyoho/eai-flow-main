"use client";

import { useParams } from "next/navigation";
import { FlowDesigner } from "@/components/workflow/designer/FlowDesigner";

export default function DesignerPage() {
  const params = useParams<{ id: string }>();
  const raw = params?.id;
  const numericId = Number(raw);
  const id = raw === "new" ? "new" : numericId;

  if (raw !== "new" && (!Number.isFinite(numericId) || numericId <= 0)) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        无效的流程定义 ID
      </div>
    );
  }

  return <FlowDesigner definitionId={raw === "new" ? "new" : (id as number)} />;
}
