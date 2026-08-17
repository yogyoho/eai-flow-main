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
    return <p className="text-muted-foreground text-sm">（无文本内容）</p>;
  }

  if (!safeHtml.trim()) {
    return (
      <p className="bg-background/80 text-foreground/80 max-h-[min(50vh,28rem)] overflow-auto rounded-lg p-3 text-sm break-words whitespace-pre-wrap">
        {raw}
      </p>
    );
  }

  return (
    <div
      className={cn(
        "chunk-html-body bg-background/80 text-foreground/80 max-h-[min(50vh,28rem)] overflow-auto rounded-lg p-3 text-sm",
        "[&_table]:w-full [&_table]:border-collapse [&_table]:text-sm",
        "[&_td]:border-border [&_td]:border [&_td]:px-2 [&_td]:py-1.5 [&_td]:align-top",
        "[&_th]:border-border [&_th]:bg-muted [&_th]:border [&_th]:px-2 [&_th]:py-1.5 [&_th]:font-medium",
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
    void (async () => {
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
      } catch (e) {
        if (!cancelled)
          toast(
            e instanceof Error && e.message ? e.message : "加载分片失败",
            "error",
          );
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
        className="bg-background relative flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl shadow-xl"
      >
        <div className="border-border flex shrink-0 items-center justify-between border-b px-6 py-4">
          <div>
            <h3 className="text-foreground text-lg font-semibold">分片数据</h3>
            <p className="text-muted-foreground mt-0.5 text-sm">
              {doc.name} · 共 {total} 个分片
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
          </Button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="text-primary h-8 w-8 animate-spin" />
            </div>
          ) : chunks.length === 0 ? (
            <div className="text-muted-foreground py-12 text-center text-sm">
              {total === 0
                ? "暂无分片数据（文档可能尚未解析完成）"
                : "暂无更多分片"}
            </div>
          ) : (
            <div className="space-y-4">
              {chunks.map((chunk, idx) => (
                <div
                  key={chunk.id ?? idx}
                  className="border-border bg-muted/50 rounded-xl border p-4"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-muted-foreground text-xs font-medium">
                      分片 #{idx + 1}
                    </span>
                    {chunk.id && (
                      <span
                        className="text-muted-foreground/70 max-w-[280px] truncate font-mono text-xs"
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
