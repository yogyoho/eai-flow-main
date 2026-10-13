"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** 原文内嵌渲染器（EAI-CUSTOM）：pdf 原生 iframe / docx-preview / SheetJS /
 *  pptx-preview / 文本 / 图片，全部按需懒加载对应库。 */

const IMAGE_EXTS = ["png", "jpg", "jpeg", "gif", "bmp", "webp"];

export function SourcePreview({
  taskId,
  fileName,
}: {
  taskId: string;
  fileName: string;
}) {
  const ext = useMemo(
    () => fileName.split(".").pop()?.toLowerCase() ?? "",
    [fileName],
  );
  const kind = useMemo(() => {
    if (ext === "pdf") return "pdf" as const;
    if (IMAGE_EXTS.includes(ext)) return "image" as const;
    if (ext === "docx" || ext === "doc") return "docx" as const;
    if (ext === "xlsx" || ext === "xlsm" || ext === "csv") return "xlsx" as const;
    if (ext === "pptx" || ext === "ppt") return "pptx" as const;
    if (ext === "txt" || ext === "md") return "text" as const;
    return "fallback" as const;
  }, [ext]);

  const docxRef = useRef<HTMLDivElement>(null);
  const pptxRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [sheetHtml, setSheetHtml] = useState<string | null>(null);

  const needsFetch = kind === "docx" || kind === "xlsx" || kind === "pptx" || kind === "text";

  useEffect(() => {
    if (!needsFetch) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setErr(null);
      try {
        const r = await fetch(`/api/extensions/translation/tasks/${taskId}/source`, {
          credentials: "include",
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const buf = await r.arrayBuffer();
        if (cancelled) return;
        if (kind === "docx") {
          const { renderAsync } = await import("docx-preview");
          if (docxRef.current) {
            docxRef.current.innerHTML = "";
            await renderAsync(buf, docxRef.current, undefined, {
              inWrapper: false,
            });
          }
        } else if (kind === "xlsx") {
          const XLSX = await import("xlsx");
          const wb = XLSX.read(buf, { type: "array" });
          const html = wb.SheetNames.map(
            (name) => {
              const ws = wb.Sheets[name];
              if (!ws) return "";
              return `<div style="margin-bottom:12px"><div style="font-weight:600;padding:4px 0">${name}</div>${XLSX.utils.sheet_to_html(
                ws,
              )}</div>`;
            },
          ).join("");
          setSheetHtml(html);
        } else if (kind === "pptx") {
          const { init } = await import("pptx-preview");
          if (pptxRef.current) {
            pptxRef.current.innerHTML = "";
            const previewer = init(pptxRef.current, {});
            void previewer.preview(buf);
          }
        } else {
          setText(new TextDecoder().decode(buf));
        }
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [taskId, kind, needsFetch]);

  const sourceUrl = `/api/extensions/translation/tasks/${taskId}/source`;

  if (kind === "pdf") {
    return <iframe title="原文预览" src={`${sourceUrl}?inline=1`} className="h-full w-full" />;
  }
  if (kind === "image") {
    return (
      <div className="flex h-full items-center justify-center overflow-auto p-2">
        <img src={sourceUrl} alt={fileName} className="max-h-full max-w-full object-contain" />
      </div>
    );
  }
  if (kind === "fallback") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
        <p>该格式暂不支持内嵌预览。</p>
        <Button variant="outline" size="sm" asChild>
          <a href={sourceUrl}>下载原件查看</a>
        </Button>
      </div>
    );
  }

  return (
    <div className={cn("h-full overflow-auto bg-white p-2", err && "bg-destructive/5")}>
      {loading && (
        <div className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 原文渲染中…
        </div>
      )}
      {err && <div className="p-3 text-sm text-destructive">原文渲染失败：{err}</div>}
      {kind === "xlsx" && sheetHtml && (
        <div className="text-xs" dangerouslySetInnerHTML={{ __html: sheetHtml }} />
      )}
      {kind === "text" && text != null && (
        <pre className="whitespace-pre-wrap break-words p-1 text-xs leading-5">{text}</pre>
      )}
      <div ref={docxRef} className={cn(kind === "docx" && !err ? "" : "hidden")} />
      <div ref={pptxRef} className={cn(kind === "pptx" && !err ? "" : "hidden")} />
    </div>
  );
}
