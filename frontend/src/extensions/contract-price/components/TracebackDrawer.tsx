"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Crosshair,
  Loader2,
  Maximize2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { authFetch } from "@/extensions/api/client";
import { contractPriceApi } from "@/extensions/contract-price/api";

interface Props {
  /** CpaDocument.id; null closes the drawer. */
  docId: string | null;
  /** 1-based page number. */
  page: number | null;
  /** Normalized [x1, y1, x2, y2] in 0~1 vs the page; null = no highlight. */
  bbox: number[] | null;
  /** CpaItem.id — 零框(paddleocr-vl 无坐标)时用于按需坐标恢复。 */
  itemId: string | null;
  onClose: () => void;
}

/**
 * Traceback overlay: fetches the OCR page preview PNG via credentialed fetch
 * (so auth cookies are sent), converts to a blob URL, and overlays a red box
 * at the item's bbox so a reviewer can eyeball whether the OCR'd price matches
 * the source.
 *
 * Zoom: wheel toward cursor, click-to-zoom at scale 1, +/-/reset buttons, and
 * drag-to-pan when zoomed. The img + bbox share one transform wrapper so the
 * highlight stays glued to its source span at every zoom level.
 */
const MIN_SCALE = 1;
const MAX_SCALE = 6;

export function TracebackDrawer({ docId, page, bbox, itemId, onClose }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // zoom + pan; one object so a zoom re-anchors atomically with its translate
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    mx: number;
    my: number;
    vx: number;
    vy: number;
  } | null>(null);

  const loadPreview = useCallback(async () => {
    if (!docId || !page) return;
    setLoading(true);
    setError(null);
    try {
      const url = contractPriceApi.previewUrl(docId, page);
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) {
        if (res.status === 404)
          throw new Error("该页无预览图（可能为非表格页或未生成预览）");
        if (res.status === 401)
          throw new Error("登录已过期，请刷新页面重新登录");
        throw new Error(`加载失败 (${res.status})`);
      }
      const blob = await res.blob();
      // revoke previous blob URL to avoid memory leak
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      setBlobUrl(URL.createObjectURL(blob));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载预览失败");
    } finally {
      setLoading(false);
    }
  }, [docId, page]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setBlobUrl(null);
    setError(null);
    setView({ scale: 1, x: 0, y: 0 });
    if (docId && page) void loadPreview();
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [docId, page]); // eslint-disable-line react-hooks/exhaustive-deps

  // esc to close
  useEffect(() => {
    if (!docId) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [docId, onClose]);

  // native non-passive wheel so we can preventDefault (React onWheel is passive)
  const zoomAt = useCallback((px: number, py: number, factor: number) => {
    setView((v) => {
      const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * factor));
      if (scale === v.scale) return v;
      // keep the image-space point under (px,py) fixed under the cursor
      const imgX = (px - v.x) / v.scale;
      const imgY = (py - v.y) / v.scale;
      return { scale, x: px - imgX * scale, y: py - imgY * scale };
    });
  }, []);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(
        e.clientX - rect.left,
        e.clientY - rect.top,
        e.deltaY < 0 ? 1.15 : 1 / 1.15,
      );
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const onMouseDown = (e: React.MouseEvent) => {
    const el = viewportRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    if (view.scale <= MIN_SCALE) {
      // click-to-zoom-in at the cursor when at fit scale
      zoomAt(px, py, 2.5);
      return;
    }
    dragRef.current = { mx: e.clientX, my: e.clientY, vx: view.x, vy: view.y };
    setDragging(true);
  };
  const onMouseMove = (e: React.MouseEvent) => {
    const d = dragRef.current;
    if (!d) return;
    setView((v) => ({
      ...v,
      x: d.vx + (e.clientX - d.mx),
      y: d.vy + (e.clientY - d.my),
    }));
  };
  const endDrag = () => {
    dragRef.current = null;
    setDragging(false);
  };

  const zoomFromCenter = (factor: number) => {
    const rect = viewportRef.current?.getBoundingClientRect();
    zoomAt(rect ? rect.width / 2 : 0, rect ? rect.height / 2 : 0, factor);
  };
  const reset = () => setView({ scale: 1, x: 0, y: 0 });

  // 零框([0,0,0,0],paddleocr-vl 标记流无坐标的占位)视为无框 → 触发按需坐标恢复
  // (hooks 须在 early return 之前)
  const stored =
    !!bbox &&
    bbox.length === 4 &&
    (bbox[2] - bbox[0] > 0.001 || bbox[3] - bbox[1] > 0.001)
      ? bbox
      : null;
  const recoverQ = useQuery({
    queryKey: ["cpa", "tracebox", docId, itemId],
    queryFn: () =>
      authFetch<{ bbox: number[] | null; page: number; source: string }>(
        `/contract-price/documents/${docId}/items/${itemId}/tracebox`,
      ),
    enabled: stored === null && !!docId && !!itemId,
    staleTime: Infinity,
    retry: false,
  });
  const box = stored ?? recoverQ.data?.bbox ?? null;

  if (!docId || !page) return null;

  const hasBox =
    !!box &&
    box.length === 4 &&
    (box[2] - box[0] > 0.001 || box[3] - box[1] > 0.001);
  const zoomed = view.scale > MIN_SCALE;
  const atRest = view.scale === 1 && view.x === 0 && view.y === 0;
  const iconBtn =
    "flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:pointer-events-none disabled:opacity-40";

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[1px]"
        onClick={onClose}
      />
      <div className="bg-card border-border relative h-full w-full max-w-2xl overflow-auto border-l shadow-2xl">
        <div className="border-border sticky top-0 z-10 flex items-center justify-between border-b bg-[var(--db-bg-tertiary)] px-5 py-3">
          <div className="flex items-center gap-2">
            <Crosshair className="h-4 w-4 text-rose-600 dark:text-rose-400" />
            <h3 className="db-text-primary text-sm font-semibold">溯源比对</h3>
            <span className="font-cyber db-text-subtle text-[10px] tracking-wider">
              PAGE {page} TRACEBACK
            </span>
            {stored === null && recoverQ.isLoading && (
              <span className="text-muted-foreground inline-flex items-center gap-1 text-[10px]">
                <Loader2 className="h-3 w-3 animate-spin" />
                坐标定位中…
              </span>
            )}
            {stored === null && recoverQ.isSuccess && !box && (
              <span className="text-[10px] text-amber-600 dark:text-amber-400">
                本页未定位到该货物
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 p-5">
          {loading ? (
            <div className="text-muted-foreground flex items-center gap-2 py-8 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载预览…
            </div>
          ) : error ? (
            <div className="rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-sm text-amber-600 dark:text-amber-400">
              {error}
            </div>
          ) : blobUrl ? (
            <div
              ref={viewportRef}
              className="border-border bg-muted/20 relative w-full touch-none overflow-hidden rounded-md border select-none"
              style={{
                cursor: zoomed ? (dragging ? "grabbing" : "grab") : "zoom-in",
              }}
              onMouseDown={onMouseDown}
              onMouseMove={onMouseMove}
              onMouseUp={endDrag}
              onMouseLeave={endDrag}
            >
              <div
                className="relative inline-block leading-none"
                style={{
                  transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
                  transformOrigin: "0 0",
                }}
              >
                <img
                  src={blobUrl}
                  alt={`第 ${page} 页预览`}
                  className="block h-auto max-w-full"
                  draggable={false}
                />
                {hasBox && box && (
                  <div
                    className="pointer-events-none absolute rounded-[2px] border-2 border-rose-500 bg-rose-500/10 shadow-[0_0_0_2px_rgba(244,63,94,0.3)]"
                    style={{
                      left: `${(box[0] ?? 0) * 100}%`,
                      top: `${(box[1] ?? 0) * 100}%`,
                      width: `${((box[2] ?? 0) - (box[0] ?? 0)) * 100}%`,
                      height: `${((box[3] ?? 0) - (box[1] ?? 0)) * 100}%`,
                    }}
                  />
                )}
              </div>

              {/* zoom toolbar */}
              <div className="border-border bg-background/90 absolute top-3 right-3 z-10 flex flex-col items-center gap-0.5 rounded-lg border p-1 shadow-md backdrop-blur">
                <button
                  onClick={() => zoomFromCenter(1.4)}
                  disabled={view.scale >= MAX_SCALE}
                  className={iconBtn}
                  aria-label="放大"
                >
                  <ZoomIn className="h-4 w-4" />
                </button>
                <span className="font-cyber db-text-subtle text-[10px] leading-tight">
                  {Math.round(view.scale * 100)}%
                </span>
                <button
                  onClick={() => zoomFromCenter(1 / 1.4)}
                  disabled={view.scale <= MIN_SCALE}
                  className={iconBtn}
                  aria-label="缩小"
                >
                  <ZoomOut className="h-4 w-4" />
                </button>
                <button
                  onClick={reset}
                  disabled={atRest}
                  className={iconBtn}
                  aria-label="重置缩放"
                >
                  <Maximize2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ) : (
            <div className="text-muted-foreground text-sm">无预览图。</div>
          )}
          <p className="db-text-subtle font-cyber text-xs tracking-wide">
            红框 = OCR 提取位置 · 对照原文核验价格数字是否正确 ·
            滚轮/点击缩放，放大后可拖动平移
          </p>
        </div>
      </div>
    </div>
  );
}
