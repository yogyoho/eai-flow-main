"use client";

import { MessageSquare } from "lucide-react";

import type { CollabComment } from "../types";

interface BlockCommentAnchorProps {
  blockId: string;
  comments: CollabComment[];
  onClick: (blockId: string) => void;
}

export function BlockCommentAnchor({
  blockId,
  comments,
  onClick,
}: BlockCommentAnchorProps) {
  const unresolvedCount = comments.filter((c) => !c.resolved).length;
  if (unresolvedCount === 0) return null;

  return (
    <button
      className="bg-primary/10 hover:bg-primary/20 group absolute top-1/2 -right-8 flex h-6 w-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full transition-colors"
      onClick={() => onClick(blockId)}
      title={`${unresolvedCount} 条评论`}
    >
      <MessageSquare className="text-primary h-3.5 w-3.5" />
      {unresolvedCount > 1 && (
        <span className="bg-primary text-primary-foreground absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-medium">
          {unresolvedCount}
        </span>
      )}
    </button>
  );
}
