"use client";

import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface PageLoadingOverlayProps {
  text?: string;
  className?: string;
}

export function PageLoadingOverlay({ text = "Loading...", className }: PageLoadingOverlayProps) {
  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex flex-col items-center justify-center bg-background/80 backdrop-blur-sm",
        className
      )}
    >
      <Loader2 className="h-10 w-10 animate-spin text-primary mb-4" />
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  );
}
