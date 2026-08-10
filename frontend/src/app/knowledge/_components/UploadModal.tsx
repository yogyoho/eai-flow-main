"use client";

import { motion } from "framer-motion";
import { Loader2, Upload, X } from "lucide-react";
import React, { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { kbApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "info";

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const CHUNK_METHOD_ACCEPT: Record<string, { extensions: string; label: string }> = {
  naive: {
    extensions: ".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.md,.csv,.json,.html,.eml,.jpg,.jpeg,.png,.gif,.bmp,.tiff",
    label: "支持 PDF、Word、Excel、PPT、TXT、Markdown、图片等格式",
  },
  manual: {
    extensions: ".pdf,.docx,.doc",
    label: "仅支持 PDF、Word 格式",
  },
  laws: {
    extensions: ".pdf,.docx,.doc",
    label: "仅支持 PDF、Word 格式",
  },
  paper: {
    extensions: ".pdf",
    label: "仅支持 PDF 格式",
  },
  book: {
    extensions: ".pdf,.docx,.doc,.txt,.md,.epub",
    label: "支持 PDF、Word、TXT、Markdown、EPUB 格式",
  },
  qa: {
    extensions: ".pdf,.docx,.doc,.xlsx,.xls,.csv",
    label: "支持 PDF、Word、Excel、CSV 格式",
  },
};

export function UploadModal({
  kbId,
  chunkMethod,
  onClose,
  onUploaded,
  toast,
}: {
  kbId: string;
  chunkMethod?: string;
  onClose: () => void;
  onUploaded: () => void;
  toast: (msg: string, type?: ToastType) => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // EAI-CUSTOM: noUncheckedIndexedAccess makes Record<string,T> lookups yield T | undefined;
  // narrow with an early guard so every downstream acceptInfo.* access is defined.
  const acceptInfo = CHUNK_METHOD_ACCEPT[chunkMethod || "naive"] ?? CHUNK_METHOD_ACCEPT.naive;
  if (!acceptInfo) {
    // Unknown chunk method — no accept config available, render nothing.
    return null;
  }

  const getFileExt = (name: string) => name.split(".").pop()?.toLowerCase() || "";

  const isFileAccepted = (file: File): boolean => {
    const ext = getFileExt(file.name);
    if (!ext) return false;
    const allowedExts = acceptInfo.extensions.split(",").map((e) => e.trim().replace(".", ""));
    return allowedExts.includes(ext);
  };

  const addFiles = (newFiles: FileList | null) => {
    if (!newFiles) return;
    const incoming = Array.from(newFiles);
    const rejected: string[] = [];
    const accepted: File[] = [];
    for (const f of incoming) {
      if (isFileAccepted(f)) {
        accepted.push(f);
      } else {
        rejected.push(f.name);
      }
    }
    if (rejected.length > 0) {
      toast(`${rejected.join("、")} 格式不受支持。${acceptInfo.label}`, "error");
    }
    if (accepted.length > 0) {
      setFiles((prev) => [...prev, ...accepted]);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  };

  const handleUpload = async () => {
    if (!files.length) return;
    setUploading(true);
    let success = 0;
    for (const file of files) {
      try {
        await kbApi.uploadDoc(kbId, file);
        success++;
      } catch (e: any) {
        toast(`${file.name} 上传失败: ${e?.message ?? "未知错误"}`, "error");
      }
    }
    setUploading(false);
    if (success > 0) {
      toast(`成功上传 ${success} 个文件`, "success");
      onUploaded();
      onClose();
    }
  };

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
        className="relative w-full max-w-lg overflow-hidden rounded-2xl bg-background shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h3 className="text-lg font-semibold text-foreground">上传文件</h3>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>
        <div className="space-y-4 p-6">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors",
              dragOver
                ? "border-primary bg-primary/10"
                : "border-input hover:border-primary/50 hover:bg-muted",
            )}
          >
            <Upload className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">
              拖拽文件到此处，或点击选择
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {acceptInfo.label}
            </p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={acceptInfo.extensions}
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
            />
          </div>
          {files.length > 0 && (
            <div className="max-h-40 space-y-2 overflow-y-auto">
              {files.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg bg-muted px-3 py-2 text-sm"
                >
                  <span className="flex-1 truncate text-foreground">
                    {f.name}
                  </span>
                  <span className="ml-2 shrink-0 text-muted-foreground">
                    {formatFileSize(f.size)}
                  </span>
                  <button
                    onClick={() =>
                      setFiles((prev) => prev.filter((_, j) => j !== i))
                    }
                    className="ml-2 shrink-0 text-muted-foreground transition-colors hover:text-destructive"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-border bg-muted/50 px-6 py-4">
          <Button
            variant="outline"
            onClick={onClose}
          >
            取消
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!files.length || uploading}
          >
            {uploading && <Loader2 className="h-4 w-4 animate-spin" />}
            上传
          </Button>
        </div>
      </motion.div>
    </div>
  );
}
