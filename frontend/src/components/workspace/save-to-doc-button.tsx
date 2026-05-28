"use client";

import { BookmarkIcon, CheckIcon, Loader2Icon, AlertCircleIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { docmgrApi } from "@/extensions/api";

import { Tooltip } from "./tooltip";

function extractTitle(content: string): string {
  const headingMatch = /^#{1,3}\s+(.+)/m.exec(content);
  if (headingMatch?.[1]) return headingMatch[1].trim().slice(0, 100);
  const firstLine = content.split("\n").find((l) => l.trim());
  return (firstLine?.trim() ?? "未命名文档").slice(0, 100);
}

export function SaveToDocButton({
  content,
  threadId,
  projectId,
}: {
  content: string;
  threadId?: string;
  projectId?: string;
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
        project_id: projectId,
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

  const icon =
    state === "saving" ? (
      <Loader2Icon className="animate-spin" size={12} />
    ) : state === "done" ? (
      <CheckIcon className="text-green-500" size={12} />
    ) : state === "error" ? (
      <AlertCircleIcon className="text-red-500" size={12} />
    ) : (
      <BookmarkIcon size={12} />
    );

  return (
    <Tooltip
      content={
        state === "error"
          ? "保存失败，请重试"
          : state === "done"
            ? "已保存"
            : "保存到文档空间"
      }
    >
      <Button
        size="icon-sm"
        type="button"
        variant="ghost"
        onClick={handleSave}
        disabled={state === "saving" || state === "done"}
      >
        {icon}
      </Button>
    </Tooltip>
  );
}
