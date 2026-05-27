"use client";

import { useCallback, useEffect, useState } from "react";
import { docmgrApi } from "../api";
import type { CollabComment, CommentCreateRequest } from "../types";

export function useComments(docId: string | null) {
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

  const createComment = useCallback(
    async (data: CommentCreateRequest) => {
      if (!docId) return;
      const comment = await docmgrApi.createComment(docId, data);
      setComments((prev) => [...prev, comment]);
      return comment;
    },
    [docId],
  );

  const updateComment = useCallback(async (commentId: string, content: string) => {
    const updated = await docmgrApi.updateComment(commentId, { content });
    setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
    return updated;
  }, []);

  const deleteComment = useCallback(async (commentId: string) => {
    await docmgrApi.deleteComment(commentId);
    setComments((prev) => prev.filter((c) => c.id !== commentId));
  }, []);

  const resolveComment = useCallback(async (commentId: string) => {
    const updated = await docmgrApi.resolveComment(commentId);
    setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
    return updated;
  }, []);

  const reopenComment = useCallback(async (commentId: string) => {
    const updated = await docmgrApi.reopenComment(commentId);
    setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
    return updated;
  }, []);

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
