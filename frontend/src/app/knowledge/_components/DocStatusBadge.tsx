"use client";

import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";

export function DocStatusBadge({ status }: { status: string }) {
  if (status === "success" || status === "done")
    return <CheckCircle2 className="text-success h-4 w-4" />;
  if (status === "uploading" || status === "processing" || status === "pending")
    return <Loader2 className="text-primary h-4 w-4 animate-spin" />;
  if (status === "failed" || status === "error")
    return <AlertCircle className="text-destructive h-4 w-4" />;
  return <Clock className="text-muted-foreground h-4 w-4" />;
}
