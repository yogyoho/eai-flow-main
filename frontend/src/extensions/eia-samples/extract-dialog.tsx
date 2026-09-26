"use client";

// EAI-CUSTOM: 煤矿环评报告样例库 二期（BS3 ③提取流水线）对话框——
// 选样例 → 运行（save=false 仅预览）→ 章节树可折叠预览 + 实体候选 → 保存入库（save=true）。

import {
  ChevronRight,
  FileSearch,
  Loader2,
  Mountain,
  Play,
  Save,
  ShieldAlert,
  Waves,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AdminSelect } from "@/components/ui/admin-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import {
  CANDIDATE_BUCKET_LABELS,
  sampleLibraryApi,
  type ExtractResult,
  type KFSampleRecord,
} from "./sample-library-api";

const SOURCE_KIND_OPTIONS = [
  { value: "auto", label: "自动识别" },
  { value: "txt", label: "TXT 文本" },
  { value: "docx", label: "DOCX 文档" },
];

const BUCKET_ICONS: Record<string, typeof Mountain> = {
  mines: Mountain,
  sensitive: ShieldAlert,
  waters: Waves,
};

const RUN_STEPS = [
  "定位源文件（.txt/.docx）",
  "章节大纲双通道提取",
  "实体候选后缀匹配",
];

export default function ExtractDialog({
  sample,
  open,
  onClose,
  onSaved,
}: {
  sample: KFSampleRecord | null;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [sourceKind, setSourceKind] = useState("auto");
  const [running, setRunning] = useState(false);
  const [step, setStep] = useState(-1); // 运行中动画步号
  const [result, setResult] = useState<ExtractResult | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (!open || !sample) return null;

  const reset = () => {
    setResult(null);
    setStep(-1);
    setRunning(false);
  };

  const run = async (save: boolean) => {
    setRunning(true);
    setResult(null);
    setStep(0);
    const timer = setInterval(
      () => setStep((s) => Math.min(s + 1, RUN_STEPS.length - 1)),
      400,
    );
    try {
      const res = await sampleLibraryApi.extract(
        sample.id,
        sourceKind as "auto",
        save,
      );
      clearInterval(timer);
      setResult(res);
      setExpanded(new Set(res.chapters.slice(0, 1).map((c) => c.no)));
      if (save) {
        toast.success(
          `已入库：${res.chapters.length} 章，实体候选 ${Object.values(res.candidates).flat().length} 个`,
        );
        onSaved();
      } else {
        toast.success(`提取完成（预览）：${res.chapters.length} 章`);
      }
    } catch (e) {
      clearInterval(timer);
      toast.error(e instanceof Error ? e.message : "提取失败");
    } finally {
      clearInterval(timer);
      setRunning(false);
      setStep(-1);
    }
  };

  const toggleChapter = (no: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(no)) next.delete(no);
      else next.add(no);
      return next;
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[720px]">
        <DialogHeader>
          <DialogTitle>提取流水线</DialogTitle>
          <DialogDescription>
            从样例源文件提取章节大纲与实体候选。运行 =
            仅预览不入库；保存入库写入 outline_json 并升级状态。
          </DialogDescription>
        </DialogHeader>

        <div className="border-border bg-muted/30 rounded-lg border px-4 py-3">
          <div className="text-foreground truncate text-sm font-medium">
            {sample.title}
          </div>
          <div className="text-muted-foreground truncate text-xs">
            {sample.source_path}
          </div>
        </div>

        <div className="flex items-end gap-3">
          <div className="grid w-48 gap-1.5">
            <span className="text-muted-foreground text-xs font-medium">
              源类型
            </span>
            <AdminSelect
              value={sourceKind}
              onValueChange={(v) => setSourceKind(v)}
              options={SOURCE_KIND_OPTIONS}
            />
          </div>
          <Button onClick={() => void run(false)} disabled={running}>
            {running ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            运行提取
          </Button>
          {result && !running && (
            <Button
              variant="outline"
              onClick={() => void run(true)}
              disabled={result.saved}
            >
              <Save className="h-4 w-4" />
              {result.saved ? "已入库" : "保存入库"}
            </Button>
          )}
        </div>

        {running && (
          <ol className="text-muted-foreground space-y-1 text-xs">
            {RUN_STEPS.map((s, i) => (
              <li
                key={s}
                className={cn(
                  "flex items-center gap-2",
                  i <= step && "text-foreground",
                )}
              >
                {i < step ? (
                  "✓"
                ) : i === step ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  "·"
                )}
                {s}
              </li>
            ))}
          </ol>
        )}

        {result && (
          <div className="space-y-4">
            <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline">
                {result.source_kind.toUpperCase()}
              </Badge>
              <span>{result.source_chars.toLocaleString()} 字符</span>
              <span>·</span>
              <span>{result.chapters.length} 章</span>
              <span>·</span>
              <span>
                实体候选{" "}
                {Object.values(result.candidates).reduce(
                  (n, v) => n + v.length,
                  0,
                )}{" "}
                个
              </span>
              {result.saved && (
                <Badge className="bg-emerald-600 text-white">已入库</Badge>
              )}
            </div>

            {/* 章节树（可折叠） */}
            <div className="border-border overflow-hidden rounded-lg border">
              <div className="bg-muted/50 text-muted-foreground border-border border-b px-3 py-2 text-xs font-medium">
                章节大纲
              </div>
              <div className="max-h-72 overflow-y-auto p-2">
                {result.chapters.length === 0 ? (
                  <p className="text-muted-foreground px-2 py-6 text-center text-sm">
                    未提取到章节——请核对源文件是否为完整报告。
                  </p>
                ) : (
                  result.chapters.map((ch) => {
                    const isOpen = expanded.has(ch.no);
                    return (
                      <div key={ch.no}>
                        <button
                          type="button"
                          onClick={() => toggleChapter(ch.no)}
                          className="hover:bg-muted/60 flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm"
                        >
                          <ChevronRight
                            className={cn(
                              "text-muted-foreground h-3.5 w-3.5 transition-transform",
                              isOpen && "rotate-90",
                            )}
                          />
                          <span className="text-muted-foreground w-14 shrink-0 font-mono text-xs">
                            {ch.no}
                          </span>
                          <span className="text-foreground truncate">
                            {ch.title}
                          </span>
                          {ch.sections.length > 0 && (
                            <span className="text-muted-foreground ml-auto text-xs">
                              {ch.sections.length} 节
                            </span>
                          )}
                        </button>
                        {isOpen && ch.sections.length > 0 && (
                          <div className="border-border/60 ml-8 border-l pl-3">
                            {ch.sections.map((sec) => (
                              <div
                                key={sec.no}
                                className="flex items-baseline gap-2 py-0.5 text-xs"
                              >
                                <span className="text-muted-foreground w-12 shrink-0 font-mono">
                                  {sec.no}
                                </span>
                                <span className="text-foreground/80 truncate">
                                  {sec.title}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* 实体候选 */}
            <div className="border-border overflow-hidden rounded-lg border">
              <div className="bg-muted/50 text-muted-foreground border-border border-b px-3 py-2 text-xs font-medium">
                实体候选（后缀词匹配，非精标）
              </div>
              <div className="space-y-2 p-3">
                {Object.entries(result.candidates).every(
                  ([, v]) => v.length === 0,
                ) ? (
                  <p className="text-muted-foreground text-sm">
                    <FileSearch className="mr-1 inline h-4 w-4" />
                    未命中实体候选。
                  </p>
                ) : (
                  Object.entries(result.candidates)
                    .filter(([, v]) => v.length > 0)
                    .map(([bucket, names]) => {
                      const Icon = BUCKET_ICONS[bucket] ?? FileSearch;
                      return (
                        <div
                          key={bucket}
                          className="flex flex-wrap items-center gap-1.5"
                        >
                          <span className="text-muted-foreground flex w-20 items-center gap-1 text-xs font-medium">
                            <Icon className="h-3.5 w-3.5" />
                            {CANDIDATE_BUCKET_LABELS[bucket] ?? bucket}
                          </span>
                          {names.slice(0, 12).map((n) => (
                            <Badge
                              key={n}
                              variant="secondary"
                              className="font-normal"
                            >
                              {n}
                            </Badge>
                          ))}
                          {names.length > 12 && (
                            <span className="text-muted-foreground text-xs">
                              +{names.length - 12}
                            </span>
                          )}
                        </div>
                      );
                    })
                )}
              </div>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              reset();
              onClose();
            }}
            disabled={running}
          >
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
