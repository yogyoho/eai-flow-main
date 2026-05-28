"use client";

import { useCallback, useEffect, useState } from "react";
import { docmgrApi } from "../api";
import type { CollabComment, CommentCreateRequest } from "../types";

export function useComments(docId: string | null, broadcastEvent?: (event: { type: string; payload: unknown }) => void) {
  const [comments, setComments] = useState<CollabComment[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    try {
      const list = await docmgrApi.listComments(docId);
      setComments(list);
    } catch {
      // handle error
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (
        detail?.type === "comment_created" ||
        detail?.type === "comment_resolved" ||
        detail?.type === "comment_reopened" ||
        detail?.type === "comment_deleted"
      ) {
        load();
      }
    };
    window.addEventListener("collab-event", handler);
    return () => {
      window.removeEventListener("collab-event", handler);
    };
  }, [load]);

  const createComment = useCallback(
    async (data: CommentCreateRequest) => {
      if (!docId) return;
      const comment = await docmgrApi.createComment(docId, data);
      setComments((prev) => [...prev, comment]);
      broadcastEvent?.({ type: "comment_created", payload: { commentId: comment.id } });
      return comment;
    },
    [docId, broadcastEvent],
  );

  const updateComment = useCallback(async (commentId: string, content: string) => {
    const updated = await docmgrApi.updateComment(commentId, { content });
    setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
    return updated;
  }, []);

  const deleteComment = useCallback(async (commentId: string) => {
    await docmgrApi.deleteComment(commentId);
    setComments((prev) => prev.filter((c) => c.id !== commentId));
    broadcastEvent?.({ type: "comment_deleted", payload: { commentId } });
  }, [broadcastEvent]);

  const resolveComment = useCallback(async (commentId: string) => {
    const updated = await docmgrApi.resolveComment(commentId);
    setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
    broadcastEvent?.({ type: "comment_resolved", payload: { commentId } });
    return updated;
  }, [broadcastEvent]);

  const reopenComment = useCallback(async (commentId: string) => {
    const updated = await docmgrApi.reopenComment(commentId);
    setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
    broadcastEvent?.({ type: "comment_reopened", payload: { commentId } });
    return updated;
  }, [broadcastEvent]);

  const getCommentsByBlock = useCallback(
    (blockId: string) => comments.filter((c) => c.block_id === blockId),
    [comments],
  );

  return {
    comments,
    loading,
    createComment,
    updateComment,
    deleteComment,
    resolveComment,
    reopenComment,
    getCommentsByBlock,
    reload: load,
  };
}
