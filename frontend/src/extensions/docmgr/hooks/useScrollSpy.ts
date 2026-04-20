"use client";

import { useEffect, useState, useCallback, useRef } from "react";

interface ScrollPosition {
  containerTop: number;
  scrollTop: number;
  containerHeight: number;
  scrollRatio: number;
}

function getRelativePosition(el: HTMLElement, container: HTMLElement) {
  const elRect = el.getBoundingClientRect();
  const containerRect = container.getBoundingClientRect();
  return {
    relativeTop: elRect.top - containerRect.top + container.scrollTop,
    relativeBottom: elRect.bottom - containerRect.top + container.scrollTop,
  };
}

export function getScrollPosition(container: HTMLElement): ScrollPosition {
  const containerRect = container.getBoundingClientRect();
  const containerTop = containerRect.top;
  const scrollTop = container.scrollTop;
  const containerHeight = container.clientHeight;
  let scrollRatio = 0;
  if (container.scrollHeight > containerHeight) {
    scrollRatio = scrollTop / (container.scrollHeight - containerHeight);
  }
  return { containerTop, scrollTop, containerHeight, scrollRatio };
}

export interface UseScrollSpyOptions {
  containerRef: React.RefObject<HTMLElement | null>;
  headings: Array<{ id: string; element: HTMLElement }>;
  offsetTop?: number;
  debounceMs?: number;
}

export function useScrollSpy({
  containerRef,
  headings,
  offsetTop = 80,
  debounceMs = 50,
}: UseScrollSpyOptions): string | null {
  const [activeId, setActiveId] = useState<string | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const handleScroll = useCallback(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      const container = containerRef.current;
      if (!container || headings.length === 0) return;
      let current: string | null = null;
      let lastValidTop = -Infinity;
      for (const heading of headings) {
        const el = heading.element;
        const isVisible = el.offsetParent !== null;
        if (!isVisible) continue;
        try {
          const { relativeTop, relativeBottom } = getRelativePosition(el, container);
          if (relativeBottom > offsetTop && relativeTop < container.clientHeight) {
            if (relativeTop > lastValidTop && relativeTop <= offsetTop) {
              lastValidTop = relativeTop;
              current = heading.id;
            }
          }
        } catch {
          continue;
        }
      }
      setActiveId(current);
    }, debounceMs);
  }, [containerRef, headings, offsetTop, debounceMs]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => {
      container.removeEventListener("scroll", handleScroll);
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [containerRef, handleScroll]);

  return activeId;
}
