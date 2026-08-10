"use client";

import { motion } from "framer-motion";
import DOMPurify from "isomorphic-dompurify";
import { Loader2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { kbApi } from "@/extensions/api";
import { type Document } from "@/extensions/types";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "info";

function chunkRawText(chunk: {
  content?: string;
  content_with_weight?: string;
  [k: string]: unknown;
}): string {
  const c = chunk.content ?? chunk.content_with_weight;
  return c != null ? String(c) : "";
}

/** Heuristic: RAGFlow often stores chunks as HTML fragments (tables, etc.). */
function looksLikeHtmlFragment(s: string): boolean {
  return /<\/?[a-z][\s\S]*?>/i.test(s);
}

export function ChunkHtmlBody({ raw }: { raw: string }) {
  const safeHtml = useMemo(() => {
    if (!raw.trim()) return "";
    if (!looksLikeHtmlFragment(raw)) return "";
    return DOMPurify.sanitize(raw, {
      USE_PROFILES: { html: true },
      ADD_ATTR: ["colspan", "rowspan", "align", "valign", "width", "height"],
    });
  }, [raw]);

  if (!raw.trim()) {
    return <p className="text-sm text-muted-foreground">（无文本内容）</p>;
  }

  if (!safeHtml.trim()) {
    return (
      <p className="max-h-[min(50vh,28rem)] overflow-auto rounded-lg bg-background/80 p-3 text-sm break-words whitespace-pre-wrap text-foreground/80">
        {raw}
      </p>
    );
  }

  return (
    <div
      className={cn(
        "chunk-html-body max-h-[min(50vh,28rem)] overflow-auto rounded-lg bg-background/80 p-3 text-sm text-foreground/80",
        "[&_table]:w-full [&_table]:border-collapse [&_table]:text-sm",
        "[&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1.5 [&_td]:align-top",
        "[&_th]:border [&_th]:border-border [&_th]:bg-muted [&_th]:px-2 [&_th]:py-1.5 [&_th]:font-medium",
        "[&_tr:nth-child(even)]:bg-muted/80",
        "[&_br]:block [&_p]:my-1",
        "[&_img]:h-auto [&_img]:max-w-full",
      )}

      dangerouslySetInnerHTML={{ __html: safeHtml }}
    />
  );
}

export function ChunkModal({
  kbId,
  doc,
  onClose,
  toast,
}: {
  kbId: string;
  doc: Document;
  onClose: () => void;
  toast: (msg: string, type?: ToastType) => void;
}) {
  const [chunks, setChunks] = useState<
    Array<{ id?: string; content?: string; [k: string]: unknown }>
  >([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await kbApi.listChunks(kbId, doc.id, {
          page: 1,
          size: 200,
        });
        if (!cancelled) {
          setChunks(res.chunks || []);
          setTotal(res.total ?? 0);
        }
      } catch (e: any) {
        if (!cancelled) toast(e?.message ?? "加载分片失败", "error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [kbId, doc.id, toast]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-background shadow-xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h3 className="text-lg font-semibold text-foreground">分片数据</h3>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {doc.name} · 共 {total} 个分片
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : chunks.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              {total === 0
                ? "暂无分片数据（文档可能尚未解析完成）"
                : "暂无更多分片"}
            </div>
          ) : (
            <div className="space-y-4">
              {chunks.map((chunk, idx) => (
                <div
                  key={chunk.id ?? idx}
                  className="rounded-xl border border-border bg-muted/50 p-4"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">
                      分片 #{idx + 1}
                    </span>
                    {chunk.id && (
                      <span
                        className="max-w-[280px] truncate font-mono text-xs text-muted-foreground/70"
                        title={String(chunk.id)}
                      >
                        {chunk.id}
                      </span>
                    )}
                  </div>
                  <ChunkHtmlBody raw={chunkRawText(chunk)} />
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
