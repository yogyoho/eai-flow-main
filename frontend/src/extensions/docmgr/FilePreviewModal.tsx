"use client";

import { Loader2, FileQuestion } from "lucide-react";
import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { docmgrApi } from "../api";
import type { AIDocument } from "../types";

interface FilePreviewModalProps {
  doc: AIDocument | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function isImageFile(mime?: string | null): boolean {
  return !!mime?.startsWith("image/");
}

export function isTextFile(mime?: string | null): boolean {
  if (!mime) return false;
  return (
    mime.startsWith("text/") ||
    mime === "application/json" ||
    mime === "application/xml" ||
    mime === "application/javascript"
  );
}

export function formatFileSize(bytes?: number | null): string {
  if (bytes == null) return "";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const val = bytes / Math.pow(1024, i);
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function FilePreviewModal({
  doc,
  open,
  onOpenChange,
}: FilePreviewModalProps) {
  const [loading, setLoading] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setPreviewContent(null);
      setError(null);
      setLoading(false);
    }
    onOpenChange(nextOpen);
  };

  const handlePreview = async () => {
    if (!doc) return;
    setLoading(true);
    setError(null);
    try {
      const res = await docmgrApi.previewDocument(doc.id);
      setPreviewContent(res.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "预览加载失败");
    } finally {
      setLoading(false);
    }
  };

  // When dialog opens with a new doc, load preview if applicable
  const handleDialogOpen = (isOpen: boolean) => {
    handleOpenChange(isOpen);
    if (isOpen && doc) {
      void handlePreview();
    }
  };

  if (!doc) return null;

  const isImage = isImageFile(doc.file_mime);
  const isText = isTextFile(doc.file_mime);
  const canPreview = isImage || isText;

  return (
    <Dialog open={open} onOpenChange={handleDialogOpen}>
      <DialogContent className="flex max-h-[80vh] max-w-2xl flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 truncate">
            {doc.title || "无标题"}
            {doc.file_size != null && (
              <span className="text-muted-foreground text-xs font-normal">
                {formatFileSize(doc.file_size)}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>
        <div className="flex min-h-[200px] flex-1 items-center justify-center overflow-hidden">
          {loading ? (
            <div className="text-muted-foreground flex flex-col items-center gap-2">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="text-sm">加载中...</span>
            </div>
          ) : error ? (
            <div className="text-destructive flex flex-col items-center gap-2">
              <FileQuestion className="h-8 w-8" />
              <span className="text-sm">{error}</span>
            </div>
          ) : !canPreview ? (
            <div className="text-muted-foreground flex flex-col items-center gap-2">
              <FileQuestion className="h-8 w-8" />
              <span className="text-sm">该文件类型暂不支持预览</span>
            </div>
          ) : isImage && doc.file_ref_path ? (
            <img
              src={doc.file_ref_path}
              alt={doc.title || "预览"}
              className="max-h-[60vh] max-w-full rounded-lg object-contain"
              onError={() => setError("图片加载失败")}
            />
          ) : previewContent ? (
            <pre className="text-foreground bg-muted/50 max-h-[60vh] w-full overflow-auto rounded-lg p-4 text-xs break-words whitespace-pre-wrap">
              {previewContent}
            </pre>
          ) : (
            <div className="text-muted-foreground flex flex-col items-center gap-2">
              <FileQuestion className="h-8 w-8" />
              <span className="text-sm">暂无预览内容</span>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
