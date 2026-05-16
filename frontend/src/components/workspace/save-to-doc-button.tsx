"use client";

import { BookmarkIcon, CheckIcon, Loader2Icon, AlertCircleIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { docmgrApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

function extractTitle(content: string): string {
  // Try first markdown heading
  const headingMatch = /^#{1,3}\s+(.+)/m.exec(content);
  if (headingMatch?.[1]) return headingMatch[1].trim().slice(0, 100);
  // Fallback: first non-empty line
  const firstLine = content.split("\n").find((l) => l.trim());
  return (firstLine?.trim() ?? "未命名文档").slice(0, 100);
}

export function SaveToDocButton({
  content,
  threadId,
}: {
  content: string;
  threadId?: string;
}) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");

  const handleSave = async () => {
    if (!content.trim() || state !== "idle") return;
    setState("saving");
    try {
      const doc = await docmgrApi.create({
        title: extractTitle(content),
        content,
        source_thread_id: threadId,
        folder: "默认文件夹",
      });
      setState("done");
      setTimeout(() => {
        router.push(`/docmgr?open=${doc.id}`);
      }, 600);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2000);
    }
  };

  return (
    <button
      onClick={handleSave}
      disabled={state === "saving" || state === "done"}
      title={
        state === "error"
          ? "保存失败，请重试"
          : state === "done"
            ? "已保存"
            : "保存到文档空间"
      }
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-md border text-xs transition-colors",
        state === "done"
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-500"
          : state === "error"
            ? "border-red-500/20 bg-red-500/10 text-red-500"
            : "border-border bg-background text-muted-foreground hover:border-primary hover:bg-primary/5 hover:text-primary",
        state === "saving" && "cursor-not-allowed opacity-60"
      )}
    >
      {state === "saving" ? (
        <Loader2Icon className="h-3.5 w-3.5 animate-spin" />
      ) : state === "done" ? (
        <CheckIcon className="h-3.5 w-3.5" />
      ) : state === "error" ? (
        <AlertCircleIcon className="h-3.5 w-3.5" />
      ) : (
        <BookmarkIcon className="h-3.5 w-3.5" />
      )}
    </button>
  );
}
