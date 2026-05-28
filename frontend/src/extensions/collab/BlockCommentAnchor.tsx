"use client";

import { MessageSquare } from "lucide-react";
import type { CollabComment } from "../types";

interface BlockCommentAnchorProps {
  blockId: string;
  comments: CollabComment[];
  onClick: (blockId: string) => void;
}

export function BlockCommentAnchor({ blockId, comments, onClick }: BlockCommentAnchorProps) {
  const unresolvedCount = comments.filter((c) => !c.resolved).length;
  if (unresolvedCount === 0) return null;

  return (
    <button
      className="absolute -right-8 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full
        bg-primary/10 hover:bg-primary/20 flex items-center justify-center
        transition-colors cursor-pointer group"
      onClick={() => onClick(blockId)}
      title={`${unresolvedCount} 条评论`}
    >
      <MessageSquare className="w-3.5 h-3.5 text-primary" />
      {unresolvedCount > 1 && (
        <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-primary text-primary-foreground
          text-[9px] flex items-center justify-center font-medium">
          {unresolvedCount}
        </span>
      )}
    </button>
  );
}
