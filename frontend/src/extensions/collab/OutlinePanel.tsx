"use client";

import { List } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HeadingItem {
  /** BlockNote block ID */
  id: string;
  /** Heading level (1–6) */
  level: number;
  /** Visible text of the heading */
  text: string;
}

interface OutlinePanelProps {
  /** BlockNote editor instance — typed loosely to avoid coupling to BlockNote internals. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  editor: any;
  /** Called when the active heading changes — passes the block id for traceability. */
  onChapterSelect?: (chapterId: string | null) => void;
  /**
   * Optional list of block IDs to show in the outline.
   * When provided and non-empty, only headings whose block ID is in this list
   * will be displayed. Used to restrict visibility based on chapter permissions.
   */
  visibleChapterIds?: string[];
}

// ---------------------------------------------------------------------------
// Heading extraction
// ---------------------------------------------------------------------------

/** Extract plain text from a BlockNote inline content array. */
function extractText(
  content: Array<Record<string, unknown>> | undefined,
): string {
  if (!content) return "";
  return content
    .map((c) => {
      if (typeof c.text === "string") return c.text;
      if (Array.isArray(c.content))
        return extractText(c.content as Array<Record<string, unknown>>);
      return "";
    })
    .join("");
}

/** Walk the editor document and collect heading blocks. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function extractHeadings(doc: any[]): HeadingItem[] {
  const result: HeadingItem[] = [];
  for (const block of doc) {
    if (block.type === "heading") {
      const level = (block.props?.level as number) ?? 1;
      const text = extractText(block.content).trim();
      if (text) {
        result.push({ id: block.id, level, text });
      }
    }
  }
  return result;
}

/**
 * Find the DOM element for a given BlockNote block ID.
 * BlockNote renders each block as `.bn-block-outer` containing a nested
 * `[data-node-id]` wrapper.  We walk upward to the outer shell for scrolling.
 */
function findBlockElement(blockId: string): HTMLElement | null {
  // Primary: data-id on .bn-block-outer (confirmed in DOM: data-id="uuid")
  const byDataId = document.querySelector(
    `.bn-block-outer[data-id="${blockId}"]`,
  );
  if (byDataId) return byDataId as HTMLElement;

  // Fallback: data-node-id attribute on the inner wrapper
  const inner = document.querySelector(`[data-node-id="${blockId}"]`);
  if (inner) return inner.closest(".bn-block-outer")! ?? (inner as HTMLElement);

  return null;
}

// ---------------------------------------------------------------------------
// Scroll spy — detect which heading is currently in viewport
// ---------------------------------------------------------------------------

function useScrollSpy(headings: HeadingItem[]): string | null {
  const [activeId, setActiveId] = useState<string | null>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (headings.length === 0) return;

    // We observe the scroll container and check heading positions
    // Instead of per-element observation (BlockNote DOM IDs aren't stable),
    // use a scroll listener approach
    const scrollContainer = document.querySelector(
      ".flex-1.overflow-y-auto.min-h-0",
    );

    const handleScroll = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        let topHeading: string | null = null;
        let topOffset = Infinity;
        for (const h of headings) {
          const el = findBlockElement(h.id);
          if (!el) continue;
          const rect = el.getBoundingClientRect();
          // Consider headings that are near the top of viewport
          if (
            rect.top < 120 &&
            rect.top > -rect.height &&
            rect.top < topOffset
          ) {
            topOffset = rect.top;
            topHeading = h.id;
          }
        }
        if (topHeading) setActiveId(topHeading);
      });
    };

    scrollContainer?.addEventListener("scroll", handleScroll, {
      passive: true,
    });
    // Run once to set initial active heading
    handleScroll();

    return () => {
      scrollContainer?.removeEventListener("scroll", handleScroll);
      cancelAnimationFrame(rafRef.current);
    };
  }, [headings]);

  return activeId;
}

// ---------------------------------------------------------------------------
// OutlinePanel component
// ---------------------------------------------------------------------------

export function OutlinePanel({
  editor,
  onChapterSelect,
  visibleChapterIds,
}: OutlinePanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [clickedId, setClickedId] = useState<string | null>(null);
  const [headings, setHeadings] = useState<HeadingItem[]>([]);

  // Filter headings to only show those matching visibleChapterIds
  const filteredHeadings = useMemo(() => {
    if (!visibleChapterIds || visibleChapterIds.length === 0) return headings;
    return headings.filter((h) => visibleChapterIds.includes(h.id));
  }, [headings, visibleChapterIds]);

  // Subscribe to editor content changes to rebuild headings reactively.
  // BlockNote's collaboration mode doesn't always expose all blocks via
  // editor.document, so we scan the DOM as a reliable source of truth.
  useEffect(() => {
    if (!editor) return;

    const rebuild = () => {
      // Strategy 1: Try the DOM first — always reliable with BlockNote collaboration
      const blocks = document.querySelectorAll(".bn-block-outer");
      const domHeadings: HeadingItem[] = [];
      blocks.forEach((b) => {
        const h1 = b.querySelector("h1");
        const h2 = b.querySelector("h2");
        const h3 = b.querySelector("h3");
        const heading = h1 ?? h2 ?? h3;
        if (heading) {
          const id = (b as HTMLElement).dataset.id ?? "";
          const level = h1 ? 1 : h2 ? 2 : 3;
          const text = heading.textContent?.trim() ?? "";
          if (id && text) {
            domHeadings.push({ id, level, text });
          }
        }
      });

      if (domHeadings.length > 0) {
        setHeadings(domHeadings);
        return;
      }

      // Strategy 2: Fallback to editor.document model
      try {
        const headings = extractHeadings(editor.document);
        if (headings.length > 0) {
          setHeadings(headings);
        }
      } catch {
        // editor.document may not be ready yet
      }
    };

    // Initial extraction
    rebuild();

    // Poll to catch Yjs sync delays (timestamps catch heading additions)
    const timers = [
      setTimeout(rebuild, 500),
      setTimeout(rebuild, 1500),
      setTimeout(rebuild, 3000),
      setTimeout(rebuild, 5000),
      setTimeout(rebuild, 8000),
    ];

    // Also try BlockNote's callback (may or may not exist)
    const unsub = editor.onEditorContentChange?.(rebuild);

    return () => {
      if (typeof unsub === "function") unsub();
      timers.forEach(clearTimeout);
    };
  }, [editor]);

  // Scroll-spy tracks the currently visible heading
  const spyId = useScrollSpy(filteredHeadings);

  // Active heading: prefer clicked (to prevent flicker), then scroll-spy
  const activeId = clickedId ?? spyId;

  // Notify parent when active heading changes (for traceability)
  useEffect(() => {
    onChapterSelect?.(activeId);
  }, [activeId, onChapterSelect]);

  // Click handler: scroll to heading block
  const handleHeadingClick = useCallback((heading: HeadingItem) => {
    setClickedId(heading.id);
    setTimeout(() => setClickedId(null), 1500);

    const el = findBlockElement(heading.id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      el.style.transition = "background-color 0.3s";
      el.style.backgroundColor = "rgba(99,102,241,0.08)";
      setTimeout(() => {
        el.style.backgroundColor = "";
      }, 1800);
    }
  }, []);

  // Don't render if no headings found
  if (filteredHeadings.length === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        "border-border bg-muted/30 flex shrink-0 flex-col border-r transition-all duration-200",
        collapsed ? "w-10" : "w-52",
      )}
    >
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between px-2 pt-3">
        {!collapsed && (
          <p className="text-muted-foreground px-1 text-[11px] font-semibold tracking-wider uppercase">
            目录
          </p>
        )}
        <Button
          size="icon"
          variant="ghost"
          className="h-6 w-6"
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? "展开目录" : "收起目录"}
        >
          <List className="text-muted-foreground h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Heading list */}
      {!collapsed && (
        <div className="scrollbar-hide flex-1 overflow-y-auto px-2 pb-4">
          <nav className="relative space-y-0.5">
            {filteredHeadings.map((h) => (
              <div key={h.id} className="group relative">
                {/* Active indicator bar */}
                <div
                  className={cn(
                    "bg-primary absolute top-0 bottom-0 left-0 w-0.5 rounded-full transition-all duration-200",
                    activeId === h.id
                      ? "opacity-100"
                      : "opacity-0 group-hover:opacity-30",
                  )}
                />
                <button
                  onClick={() => handleHeadingClick(h)}
                  title={h.text}
                  className={cn(
                    "w-full cursor-pointer rounded-r py-1 pr-2 text-left text-[13px] leading-snug transition-colors",
                    h.level === 1 && "pl-3 font-medium",
                    h.level === 2 && "pl-5",
                    h.level >= 3 && "pl-7",
                    activeId === h.id
                      ? "text-primary bg-primary/10 font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/60",
                  )}
                >
                  {h.text.length > 28 ? `${h.text.slice(0, 28)}…` : h.text}
                </button>
              </div>
            ))}
          </nav>
        </div>
      )}
    </div>
  );
}
