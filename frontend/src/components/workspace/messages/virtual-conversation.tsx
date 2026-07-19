"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ArrowDownIcon } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

// ── VirtualChatContainer ───────────────────────────────────────────────
// Drop-in replacement for <Conversation> + <ConversationContent>.
// Virtualizes the message list: only visible + overscan items render.
// Auto-scrolls to bottom when new messages arrive (if user is at bottom).

export type VirtualChatContainerProps = {
  className?: string;
  /** Total number of message groups. */
  itemCount: number;
  /** Render a single message group by index. */
  renderItem: (index: number) => ReactNode;
  /** Rendered above the virtual list (e.g. LoadMoreHistoryIndicator). */
  header?: ReactNode;
  /** Overscan count. */
  overscan?: number;
};

export function VirtualChatContainer({
  className,
  itemCount,
  renderItem,
  header,
  overscan = 5,
}: VirtualChatContainerProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  const virtualizer = useVirtualizer({
    count: itemCount,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 200,
    overscan,
    measureElement:
      typeof window !== "undefined" &&
      (navigator as { userAgent?: string }).userAgent?.includes?.("")
        ? undefined
        : undefined,
  });

  // Auto-scroll when itemCount grows (new streaming messages)
  const prevCountRef = useRef(itemCount);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const grew = itemCount > prevCountRef.current;
    prevCountRef.current = itemCount;
    if (grew && isAtBottomRef.current) {
      requestAnimationFrame(() => {
        el.scrollTo({ top: el.scrollHeight, behavior: "instant" as ScrollBehavior });
      });
    }
  }, [itemCount]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = dist < 80;
    isAtBottomRef.current = atBottom;
    setShowScrollButton(!atBottom);
  }, []);

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, []);

  const vItems = virtualizer.getVirtualItems();

  return (
    <div className={cn("relative flex-1 overflow-hidden", className)} role="log">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="h-full overflow-auto"
      >
        {header}
        <div
          className="mx-auto w-full max-w-(--container-width-md)"
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            position: "relative",
          }}
        >
          {/* Pre-render spacer for initial total height, then virtual items */}
          {vItems.map((v) => {
            const top = v.start - (vItems[0]?.start ?? 0);
            return (
              <div
                key={v.key}
                data-index={v.index}
                ref={virtualizer.measureElement}
                className="absolute left-0 top-0 w-full"
                style={{ transform: `translateY(${v.start}px)` }}
              >
                {renderItem(v.index)}
              </div>
            );
          })}
        </div>
      </div>
      {showScrollButton && (
        <Button
          className="absolute bottom-4 left-[50%] z-10 translate-x-[-50%] rounded-full shadow-lg"
          onClick={scrollToBottom}
          size="icon"
          type="button"
          variant="outline"
        >
          <ArrowDownIcon className="size-4" />
        </Button>
      )}
    </div>
  );
}
