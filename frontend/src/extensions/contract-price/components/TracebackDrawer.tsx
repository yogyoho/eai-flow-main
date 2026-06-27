"use client";

import { Crosshair, X } from "lucide-react";
import { useEffect, useState } from "react";

import { contractPriceApi } from "@/extensions/contract-price/api";

interface Props {
  /** CpaDocument.id; null closes the drawer. */
  docId: string | null;
  /** 1-based page number. */
  page: number | null;
  /** Normalized [x1, y1, x2, y2] in 0~1 vs the page; null = no highlight. */
  bbox: number[] | null;
  onClose: () => void;
}

/**
 * Traceback overlay: pulls the OCR page preview PNG and overlays a red box at
 * the item's bbox so a reviewer can eyeball whether the OCR'd price matches
 * the source. This is the human-in-the-loop half of the price-validation
 * loop — needs_review items are meaningless without a way to see the original.
 *
 * Style mirrors the dashboard: db-card surface, font-cyber accents.
 */
export function TracebackDrawer({ docId, page, bbox, onClose }: Props) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    setSrc(docId && page ? contractPriceApi.previewUrl(docId, page) : null);
  }, [docId, page]);

  // esc to close
  useEffect(() => {
    if (!docId) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [docId, onClose]);

  if (!docId || !page) return null;

  const hasBox = !!bbox && bbox.length === 4;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[1px]" onClick={onClose} />
      <div className="relative w-full max-w-2xl h-full bg-card border-l border-border shadow-2xl overflow-auto">
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-3 border-b border-border bg-[var(--db-bg-tertiary)]">
          <div className="flex items-center gap-2">
            <Crosshair className="w-4 h-4 text-rose-500" />
            <h3 className="text-sm font-semibold db-text-primary">溯源比对</h3>
            <span className="text-[10px] font-cyber tracking-wider db-text-subtle">
              PAGE {page} TRACEBACK
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          {src ? (
            <div className="relative inline-block leading-none">
              <img
                src={src}
                alt={`第 ${page} 页预览`}
                className="max-w-full h-auto rounded-md border border-border"
              />
              {hasBox && (
                <div
                  className="absolute border-2 border-rose-500 bg-rose-500/10 pointer-events-none rounded-[2px] shadow-[0_0_0_2px_rgba(244,63,94,0.3)]"
                  style={{
                    left: `${(bbox?.[0] ?? 0) * 100}%`,
                    top: `${(bbox?.[1] ?? 0) * 100}%`,
                    width: `${((bbox?.[2] ?? 0) - (bbox?.[0] ?? 0)) * 100}%`,
                    height: `${((bbox?.[3] ?? 0) - (bbox?.[1] ?? 0)) * 100}%`,
                  }}
                />
              )}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">无预览图。</div>
          )}
          <p className="text-xs db-text-subtle font-cyber tracking-wide">
            红框 = OCR 提取位置 · 对照原文核验价格数字是否正确
          </p>
        </div>
      </div>
    </div>
  );
}
