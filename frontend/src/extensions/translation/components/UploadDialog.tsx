"use client";

import { FileUp, FolderOpen, X } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/** 资产库上传对话框（结构复刻 contract-price 上传合同对话框，EAI-CUSTOM）。

  onUpload: 必须解析为逐文件结果；失败的文件留在选择列表供重试。
*/
export function UploadDialog({
  open,
  onOpenChange,
  onUpload,
  uploading,
  kbId,
  kbOptions,
  onKbChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onUpload: (
    files: File[],
    autoTranslate: boolean,
  ) => Promise<{
    total: number;
    failed: File[];
    /** 内容重复被复用的文件（后端同 KB 同 sha 幂等）。 */
    reused?: { file: string; existing_file?: string | null }[];
    message?: string;
  }>;
  uploading: boolean;
  kbId: string;
  kbOptions: { id: string; name: string }[];
  onKbChange: (id: string) => void;
}) {
  const [selected, setSelected] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [autoTranslate, setAutoTranslate] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  /** v1 支持类型：pdf/docx/xlsx/pptx/txt/md（图片 OCR 走 pdf 封装，二期）。 */
  const SUPPORTED = [
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xlsm",
    ".pptx",
    ".ppt",
    ".txt",
    ".md",
  ];

  const addFiles = (files: FileList | File[]) => {
    const supported = Array.from(files).filter((f) => {
      const ext = `.${f.name.toLowerCase().split(".").pop() ?? ""}`;
      return SUPPORTED.includes(ext);
    });
    setSelected((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}-${f.size}`));
      return [...prev, ...supported.filter((f) => !seen.has(`${f.name}-${f.size}`))];
    });
  };

  /** 开始上传：全部成功 → 清空并自动关闭；请求级失败 → 保持打开并报错。 */
  const startUpload = async () => {
    if (selected.length === 0 || uploading) return;
    setUploadError(null);
    setUploadNotice(null);
    try {
      const { failed, reused = [], message } = await onUpload(
        selected,
        autoTranslate,
      );
      if (failed.length === 0) {
        if (reused.length > 0) {
          // 内容重复：说明未新建、已有任务名，保持弹窗打开，避免“静默成功”
          setSelected([]);
          setAutoTranslate(false);
          setUploadNotice(
            `${reused.length} 个文件与知识库中已有任务内容重复，未新建任务：` +
              reused
                .map(
                  (r) =>
                    `${r.file}${r.existing_file ? `（已有：${r.existing_file}）` : ""}`,
                )
                .join("；"),
          );
          return;
        }
        setSelected([]);
        setAutoTranslate(false);
        onOpenChange(false);
      } else {
        const failedKeys = new Set(failed.map((f) => `${f.name}-${f.size}`));
        setSelected((prev) => prev.filter((f) => failedKeys.has(`${f.name}-${f.size}`)));
        setUploadError(
          (message ? `${message} — ` : "") +
            `${failed.length} 个文件上传失败，已保留在选择列表，可直接重试或移除。`,
        );
      }
    } catch (e) {
      setUploadError(`上传失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) {
          setSelected([]);
          setAutoTranslate(false);
          setUploadError(null);
          setUploadNotice(null);
        }
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>上传</DialogTitle>
          <DialogDescription>支持批量选择 EN/FR 文档或整个文件夹。</DialogDescription>
        </DialogHeader>

        {/* Drag-drop zone */}
        <div
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 transition-colors ${
            dragOver
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/30 hover:border-muted-foreground/50"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            addFiles(e.dataTransfer.files);
          }}
          onClick={() => fileRef.current?.click()}
        >
          <FileUp className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">拖拽文档到此处</p>
          <p className="text-xs text-muted-foreground">或点击选择文件 · 支持多选</p>
        </div>

        {/* 目标 RAG 知识库 */}
        <div className="grid grid-cols-[110px_1fr] items-center gap-2 text-sm">
          <span className="text-xs text-muted-foreground">目标知识库</span>
          {kbOptions.length === 0 ? (
            <span className="text-xs text-destructive">无可用库——请先在设置页「RAG知识库配置」创建</span>
          ) : (
            <Select value={kbId} onValueChange={onKbChange}>
              <SelectTrigger
                size="sm"
                className="w-full text-[13px]"
                aria-label="目标知识库"
              >
                <SelectValue placeholder="选择知识库" />
              </SelectTrigger>
              <SelectContent>
                {kbOptions.map((k) => (
                  <SelectItem key={k.id} value={k.id} className="text-[13px]">
                    {k.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Auto-translate toggle */}
        <label className="flex cursor-pointer select-none items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={autoTranslate}
            onChange={(e) => setAutoTranslate(e.target.checked)}
            className="accent-primary"
          />
          <span className={autoTranslate ? "font-medium text-foreground" : "text-muted-foreground"}>
            上传后自动翻译
          </span>
          <span className="text-xs text-muted-foreground">
            {autoTranslate
              ? "（上传完即加入翻译队列）"
              : "（上传后需勾选并点「翻译」）"}
          </span>
        </label>

        {/* Browse buttons */}
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="flex-1"
            onClick={() => fileRef.current?.click()}
          >
            <FileUp className="h-4 w-4" /> 选择文件
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="flex-1"
            onClick={() => folderRef.current?.click()}
          >
            <FolderOpen className="h-4 w-4" /> 选择文件夹
          </Button>
        </div>

        {/* Hidden inputs */}
        <input
          ref={fileRef}
          type="file"
          accept={SUPPORTED.join(",")}
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <input
          ref={folderRef}
          type="file"
          multiple
          className="hidden"
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
        />

        {/* Selected files list */}
        {selected.length > 0 && (
          <div className="max-h-48 space-y-1 overflow-y-auto">
            <p className="text-xs text-muted-foreground">
              已选 {selected.length} 个文件 · 共{" "}
              {(selected.reduce((s, f) => s + f.size, 0) / 1048576).toFixed(1)} MB
            </p>
            {selected.map((f, i) => (
              <div
                key={`${f.name}-${i}`}
                className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-1.5 text-sm"
              >
                <span className="flex-1 truncate">{f.name}</span>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {(f.size / 1048576).toFixed(1)}MB
                  </span>
                  {!uploading && (
                    <button
                      onClick={() =>
                        setSelected((prev) => prev.filter((_, j) => j !== i))
                      }
                      className="text-destructive hover:text-destructive/80"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {uploadNotice && (
          <p className="bg-info/10 text-[var(--info-900)] rounded-md px-3 py-2 text-xs">
            {uploadNotice}
          </p>
        )}
        {uploadError && <p className="text-sm text-destructive">{uploadError}</p>}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              setSelected([]);
              onOpenChange(false);
            }}
          >
            取消
          </Button>
          <Button disabled={selected.length === 0 || uploading} onClick={() => void startUpload()}>
            <FileUp className="h-4 w-4" />
            {uploading ? "上传中…" : `开始上传 (${selected.length})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
