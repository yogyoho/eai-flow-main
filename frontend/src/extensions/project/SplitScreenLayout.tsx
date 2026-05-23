"use client";

import { type ReactNode, useCallback, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface SplitScreenLayoutProps {
  left: ReactNode;
  right: ReactNode;
  defaultLeftWidth?: number;
  minLeftWidth?: number;
  maxLeftWidth?: number;
}

export function SplitScreenLayout({
  left,
  right,
  defaultLeftWidth = 300,
  minLeftWidth = 200,
  maxLeftWidth = 500,
}: SplitScreenLayoutProps) {
  const [leftWidth, setLeftWidth] = useState(defaultLeftWidth);
  const isDragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback(() => {
    isDragging.current = true;
    const onMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const newWidth = Math.min(maxLeftWidth, Math.max(minLeftWidth, e.clientX - rect.left));
      setLeftWidth(newWidth);
    };
    const onUp = () => {
      isDragging.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [minLeftWidth, maxLeftWidth]);

  return (
    <div ref={containerRef} className="flex flex-1 min-h-0 overflow-hidden">
      <div style={{ width: leftWidth }} className="shrink-0 overflow-y-auto border-r border-border">
        {left}
      </div>
      <div
        className="w-1 cursor-col-resize bg-border hover:bg-primary/30 transition-colors shrink-0"
        onMouseDown={handleMouseDown}
      />
      <div className="flex-1 min-w-0 overflow-y-auto">
        {right}
      </div>
    </div>
  );
}