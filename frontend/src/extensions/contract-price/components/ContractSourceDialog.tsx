"use client";

import { Download, FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { contractPriceApi } from "@/extensions/contract-price/api";

export interface ContractSourceDoc {
  id: string;
  file_name: string;
  /** "pdf" / "docx" / ...;小写比较。 */
  file_type: string | null;
}

/** 合同原文查看 Dialog。
 * preview PNG 只存"含提取表格的页"(溯源用途),不能当全文档预览——
 * 这里直接 iframe 内嵌 file 端点 ?inline=1,浏览器原生 PDF 查看器
 * (缩放/翻页/打印全有,盖章手写全可见)。docx 内嵌不可靠 → 只留下载。
 * iframe 的 onError 对 HTTP 错误(404/401 渲染成错误页)不可靠,
 * 打开时先 HEAD 预检一次,失败态给「下载原件」兜底。 */
export function ContractSourceDialog({
  doc,
  open,
  onOpenChange,
}: {
  doc: ContractSourceDoc | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [loadFailed, setLoadFailed] = useState(false);

  const isPdf = (doc?.file_type ?? "").toLowerCase() === "pdf";

  // 打开/换文档:复位失败态;PDF 先 HEAD 预检 file 端点(带 cookie)。
  // 405 = 后端不支持 HEAD,视为探测不出,放行 iframe。
  useEffect(() => {
    setLoadFailed(false);
    if (!open || !doc || !isPdf) return;
    let cancelled = false;
    const probe = async () => {
      try {
        const res = await fetch(contractPriceApi.fileInlineUrl(doc.id), {
          method: "HEAD",
          credentials: "include",
        });
        if (!cancelled && !res.ok && res.status !== 405) setLoadFailed(true);
      } catch {
        if (!cancelled) setLoadFailed(true);
      }
    };
    void probe();
    return () => {
      cancelled = true;
    };
  }, [open, doc, isPdf]);

  if (!doc) return null;

  const downloadBtn = (
    <Button size="sm" variant="outline" asChild>
      <a href={contractPriceApi.fileUrl(doc.id)} title="下载原始 PDF/DOCX 文件">
        <Download className="h-3.5 w-3.5" />
        下载原件
      </a>
    </Button>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-full overflow-y-auto sm:max-w-[90vw]">
        <DialogHeader>
          <DialogTitle className="truncate" title={doc.file_name}>
            合同原文 · {doc.file_name}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col items-center gap-3">
          {!isPdf ? (
            // docx 等类型 iframe 内嵌不可靠,直接引导下载
            <div className="flex h-[40vh] w-full flex-col items-center justify-center gap-3 rounded-md border border-dashed">
              <FileText className="text-muted-foreground h-8 w-8" />
              <p className="text-muted-foreground text-sm">
                该文件为 DOCX,请使用下载原件本地查看。
              </p>
              {downloadBtn}
            </div>
          ) : loadFailed ? (
            <div className="flex h-[60vh] w-full flex-col items-center justify-center gap-3">
              <p className="text-muted-foreground text-sm">
                原文加载失败,请使用下载原件。
              </p>
              {downloadBtn}
            </div>
          ) : (
            <iframe
              src={contractPriceApi.fileInlineUrl(doc.id)}
              title="合同原文"
              className="border-border h-[75vh] w-full rounded-md border"
              onError={() => setLoadFailed(true)}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
