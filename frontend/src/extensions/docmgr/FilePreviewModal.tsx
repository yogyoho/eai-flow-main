"use client";

import { Loader2, FileQuestion } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import type { AIDocument } from "../types";
import { docmgrApi } from "../api";

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

export default function FilePreviewModal({ doc, open, onOpenChange }: FilePreviewModalProps) {
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
      handlePreview();
    }
  };

  if (!doc) return null;

  const isImage = isImageFile(doc.file_mime);
  const isText = isTextFile(doc.file_mime);
  const canPreview = isImage || isText;

  return (
    <Dialog open={open} onOpenChange={handleDialogOpen}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 truncate">
            {doc.title || "无标题"}
            {doc.file_size != null && (
              <span className="text-xs font-normal text-muted-foreground">
                {formatFileSize(doc.file_size)}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-hidden flex items-center justify-center min-h-[200px]">
          {loading ? (
            <div className="flex flex-col items-center gap-2 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin" />
              <span className="text-sm">加载中...</span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center gap-2 text-destructive">
              <FileQuestion className="w-8 h-8" />
              <span className="text-sm">{error}</span>
            </div>
          ) : !canPreview ? (
            <div className="flex flex-col items-center gap-2 text-muted-foreground">
              <FileQuestion className="w-8 h-8" />
              <span className="text-sm">该文件类型暂不支持预览</span>
            </div>
          ) : isImage && doc.file_ref_path ? (
            <img
              src={doc.file_ref_path}
              alt={doc.title || "预览"}
              className="max-w-full max-h-[60vh] object-contain rounded-lg"
              onError={() => setError("图片加载失败")}
            />
          ) : previewContent ? (
            <pre className="text-xs text-foreground whitespace-pre-wrap break-words max-h-[60vh] overflow-auto w-full bg-muted/50 rounded-lg p-4">
              {previewContent}
            </pre>
          ) : (
            <div className="flex flex-col items-center gap-2 text-muted-foreground">
              <FileQuestion className="w-8 h-8" />
              <span className="text-sm">暂无预览内容</span>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
