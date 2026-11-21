"use client";

import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface PageLoadingOverlayProps {
  text?: string;
  className?: string;
}

export function PageLoadingOverlay({
  text = "Loading...",
  className,
}: PageLoadingOverlayProps) {
  return (
    <div
      className={cn(
        "bg-background/80 fixed inset-0 z-50 flex flex-col items-center justify-center backdrop-blur-sm",
        className,
      )}
    >
      <Loader2 className="text-primary mb-4 h-10 w-10 animate-spin" />
      <p className="text-muted-foreground text-sm">{text}</p>
    </div>
  );
}
