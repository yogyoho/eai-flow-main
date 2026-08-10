"use client";

import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";

export function DocStatusBadge({ status }: { status: string }) {
  if (status === "success" || status === "done")
    return <CheckCircle2 className="h-4 w-4 text-success" />;
  if (status === "uploading" || status === "processing" || status === "pending")
    return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  if (status === "failed" || status === "error")
    return <AlertCircle className="h-4 w-4 text-destructive" />;
  return <Clock className="h-4 w-4 text-muted-foreground" />;
}
