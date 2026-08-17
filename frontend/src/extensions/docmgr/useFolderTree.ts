"use client";

import { useState, useCallback, useEffect } from "react";

import { folderApi, type FolderNode } from "@/extensions/api";

export function useFolderTree(projectScope?: string, docType?: string) {
  const [folders, setFolders] = useState<FolderNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  const fetchTree = useCallback(async () => {
    setLoading(true);
    try {
      const params: { project_scope?: string; doc_type?: string } = {};
      if (projectScope) params.project_scope = projectScope;
      if (docType) params.doc_type = docType;
      const data = await folderApi.getTree(params);
      setFolders(data.folders);
    } catch (err) {
      console.error("Failed to fetch folder tree:", err);
    } finally {
      setLoading(false);
    }
  }, [projectScope, docType]);

  useEffect(() => {
    void fetchTree();
  }, [fetchTree]);

  const toggleExpand = useCallback((folderId: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) {
        next.delete(folderId);
      } else {
        next.add(folderId);
      }
      return next;
    });
  }, []);

  const createFolder = useCallback(
    async (name: string, parentId: string | null, projectId?: string) => {
      const folder = await folderApi.create({
        name,
        parent_id: parentId ?? undefined,
        project_id: projectId,
      });
      await fetchTree();
      // Auto-expand parent
      if (parentId) {
        setExpandedKeys((prev) => new Set(prev).add(parentId));
      }
      return folder;
    },
    [fetchTree],
  );

  const renameFolder = useCallback(
    async (folderId: string, name: string) => {
      await folderApi.rename(folderId, name);
      await fetchTree();
    },
    [fetchTree],
  );

  const deleteFolder = useCallback(
    async (folderId: string) => {
      await folderApi.delete(folderId);
      await fetchTree();
    },
    [fetchTree],
  );

  return {
    folders,
    loading,
    expandedKeys,
    toggleExpand,
    createFolder,
    renameFolder,
    deleteFolder,
    refreshTree: fetchTree,
  };
}
