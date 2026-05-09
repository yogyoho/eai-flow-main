"use client";

import { BookmarkIcon, CheckIcon, Loader2Icon, AlertCircleIcon } from "lucide-react";
import { useCallback, useState } from "react";

import { urlOfArtifact } from "@/core/artifacts/utils";
import { getFileName } from "@/core/utils/files";
import { docmgrApi } from "@/extensions/api";
import { cn } from "@/lib/utils";

/** Check if a document with the same title and source_thread_id already exists */
async function checkDocExists(title: string, threadId: string): Promise<boolean> {
  try {
    const result = await docmgrApi.list({ q: title });
    return result.documents.some(
      (doc) => doc.title === title && doc.source_thread_id === threadId
    );
  } catch {
    return false;
  }
}

/** Fetch artifact content and save it to the document space. */
export function SaveArtifactToDocButton({
  filepath,
  threadId,
  variant = "button",
}: {
  filepath: string;
  threadId: string;
  variant?: "button" | "icon";
}) {
  const [state, setState] = useState<"idle" | "checking" | "saving" | "done" | "exists" | "error">("idle");

  const handleSave = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (state !== "idle") return;

    const title = getFileName(filepath).replace(/\.[^.]+$/, "") || "未命名文档";

    // Check if document already exists
    setState("checking");
    try {
      const exists = await checkDocExists(title, threadId);
      if (exists) {
        setState("exists");
        setTimeout(() => setState("idle"), 3000);
        return;
      }
    } catch {
      // Continue even if check fails
    }

    setState("saving");
    try {
      const url = urlOfArtifact({ filepath, threadId });
      const res = await fetch(url);
      if (!res.ok) throw new Error("fetch failed");
      const content = await res.text();

      await docmgrApi.create({
        title,
        content,
        source_thread_id: threadId,
        folder: "默认文件夹",
      });
      setState("done");
      setTimeout(() => setState("idle"), 3000);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2000);
    }
  }, [filepath, threadId, state]);

  const title =
    state === "done" ? "已保存到文档空间" :
    state === "exists" ? "文档已存在" :
    state === "error" ? "保存失败，请重试" :
    state === "checking" ? "检查中..." :
    state === "saving" ? "保存中..." :
    "保存到文档空间";

  if (variant === "icon") {
    return (
      <button
        onClick={handleSave}
        disabled={state === "saving" || state === "done" || state === "checking" || state === "exists"}
        title={title}
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-md border text-xs transition-colors",
          state === "done"
            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-500"
            : state === "exists"
              ? "border-amber-500/20 bg-amber-500/10 text-amber-500"
              : state === "error"
                ? "border-red-500/20 bg-red-500/10 text-red-500"
                : "border-border bg-background text-muted-foreground hover:border-primary/50 hover:bg-primary/5 hover:text-primary",
          (state === "saving" || state === "checking") && "cursor-not-allowed opacity-60"
        )}
      >
        {state === "saving" || state === "checking" ? (
          <Loader2Icon className="w-3.5 h-3.5 animate-spin" />
        ) : state === "done" ? (
          <CheckIcon className="w-3.5 h-3.5" />
        ) : state === "exists" ? (
          <AlertCircleIcon className="w-3.5 h-3.5" />
        ) : state === "error" ? (
          <AlertCircleIcon className="w-3.5 h-3.5" />
        ) : (
          <BookmarkIcon className="w-3.5 h-3.5" />
        )}
      </button>
    );
  }

  return (
    <button
      onClick={handleSave}
      disabled={state === "saving" || state === "done" || state === "checking" || state === "exists"}
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
        state === "done"
          ? "text-emerald-500 bg-emerald-500/10"
          : state === "exists"
            ? "text-amber-500 bg-amber-500/10"
            : state === "error"
              ? "text-red-500 bg-red-500/10"
              : "text-muted-foreground hover:bg-muted",
        (state === "saving" || state === "checking") && "cursor-not-allowed opacity-60"
      )}
    >
      {state === "saving" || state === "checking" ? (
        <Loader2Icon className="w-4 h-4 animate-spin" />
      ) : state === "done" ? (
        <CheckIcon className="w-4 h-4" />
      ) : state === "exists" ? (
        <AlertCircleIcon className="w-4 h-4" />
      ) : state === "error" ? (
        <AlertCircleIcon className="w-4 h-4" />
      ) : (
        <BookmarkIcon className="w-4 h-4" />
      )}
      {state === "done" ? "已保存" : state === "exists" ? "已存在" : state === "error" ? "失败" : "保存"}
    </button>
  );
}

/** Only show for text-based files that make sense to save as documents */
export function isSavableToDoc(filepath: string): boolean {
  const ext = filepath.split(".").pop()?.toLowerCase() ?? "";
  return ["md", "txt", "markdown", "rst", "html"].includes(ext);
}
