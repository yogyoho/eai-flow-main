"use client";

import { BookmarkIcon, CheckIcon, Loader2Icon, AlertCircleIcon, RefreshCwIcon } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { urlOfArtifact } from "@/core/artifacts/utils";
import { getFileName } from "@/core/utils/files";
import { docmgrApi } from "@/extensions/api";

import { Tooltip } from "../tooltip";

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

  const tooltip =
    state === "done" ? "已保存到文档空间" :
    state === "exists" ? "文档已存在" :
    state === "error" ? "保存失败，请重试" :
    state === "checking" ? "检查中..." :
    state === "saving" ? "保存中..." :
    "保存到文档空间";

  const icon =
    state === "saving" || state === "checking" ? (
      <Loader2Icon className="animate-spin" size={12} />
    ) : state === "done" ? (
      <CheckIcon className="text-green-500" size={12} />
    ) : state === "exists" ? (
      <AlertCircleIcon className="text-amber-500" size={12} />
    ) : state === "error" ? (
      <AlertCircleIcon className="text-red-500" size={12} />
    ) : (
      <BookmarkIcon size={12} />
    );

  if (variant === "icon") {
    return (
      <Tooltip content={tooltip}>
        <Button
          size="icon-sm"
          type="button"
          variant="ghost"
          onClick={handleSave}
          disabled={state === "saving" || state === "done" || state === "checking" || state === "exists"}
        >
          {icon}
        </Button>
      </Tooltip>
    );
  }

  return (
    <Tooltip content={tooltip}>
      <Button
        size="sm"
        type="button"
        variant="ghost"
        onClick={handleSave}
        disabled={state === "saving" || state === "done" || state === "checking" || state === "exists"}
        className="gap-1.5"
      >
        {icon}
        {state === "done" ? "已保存" : state === "exists" ? "已存在" : state === "error" ? "失败" : "保存"}
      </Button>
    </Tooltip>
  );
}

export function isSavableToDoc(filepath: string): boolean {
  const ext = filepath.split(".").pop()?.toLowerCase() ?? "";
  return ["md", "txt", "markdown", "rst", "html"].includes(ext);
}

export function SyncToDocSpaceButton({
  threadId,
}: {
  threadId: string;
}) {
  const [state, setState] = useState<"idle" | "syncing" | "done" | "error">("idle");

  const handleSync = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (state !== "idle") return;

    setState("syncing");
    try {
      const result = await docmgrApi.syncThreadFiles(threadId);
      const total = result.synced + result.skipped;
      toast.success(`已同步 ${total} 个文件`);
      setState("done");
      setTimeout(() => setState("idle"), 3000);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2000);
    }
  }, [threadId, state]);

  const tooltip =
    state === "done" ? "已同步" :
    state === "error" ? "同步失败，请重试" :
    state === "syncing" ? "同步中..." :
    "同步到文档空间";

  const icon =
    state === "syncing" ? (
      <RefreshCwIcon className="animate-spin" size={12} />
    ) : state === "done" ? (
      <CheckIcon className="text-green-500" size={12} />
    ) : state === "error" ? (
      <AlertCircleIcon className="text-red-500" size={12} />
    ) : (
      <RefreshCwIcon size={12} />
    );

  return (
    <Tooltip content={tooltip}>
      <Button
        size="icon-sm"
        type="button"
        variant="ghost"
        onClick={handleSync}
        disabled={state === "syncing" || state === "done"}
      >
        {icon}
      </Button>
    </Tooltip>
  );
}
