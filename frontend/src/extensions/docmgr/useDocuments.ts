"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { docmgrApi } from "../api";
import type { AIDocument, CreateAIDocumentRequest, UpdateAIDocumentRequest } from "../types";

export interface DocumentFilter {
  folder?: string;
  starred?: boolean;
  shared?: boolean;
  q?: string;
}

const PAGE_SIZE = 12;

export function useDocuments(initialFilter?: DocumentFilter) {
  const [docs, setDocs] = useState<AIDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(PAGE_SIZE);
  const [folders, setFolders] = useState<string[]>([]);
  const filterRef = useRef<DocumentFilter>(initialFilter ?? { folder: "默认文件夹" });

  const load = useCallback(async (currentPage: number, currentFilter: DocumentFilter) => {
    setLoading(true);
    try {
      const res = await docmgrApi.list({
        folder: currentFilter.folder,
        starred: currentFilter.starred,
        shared: currentFilter.shared,
        q: currentFilter.q,
        skip: (currentPage - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setDocs(res.documents);
      setTotal(res.total);
    } catch {
      // handle error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    try {
      const res = docmgrApi.listFolders();
      res.then((r) => setFolders(r.folders));
    } catch {
      // keep default
    }
  }, []);

  // Reset to page 1 when filter changes; otherwise load current page
  useEffect(() => {
    setPage((prev) => {
      const nextPage = 1;
      if (prev !== nextPage) return nextPage;
      load(nextPage, filterRef.current);
      return prev;
    });
  }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  const setFilter = useCallback(
    (newFilter: DocumentFilter) => {
      filterRef.current = newFilter;
      setPage(1);
      load(1, newFilter);
    },
    [load]
  );

  const createDoc = useCallback(
    async (data: CreateAIDocumentRequest) => {
      const doc = await docmgrApi.create(data);
      await load(1, filterRef.current);
      setPage(1);
      return doc;
    },
    [load]
  );

  const updateDoc = useCallback(
    async (id: string, data: UpdateAIDocumentRequest): Promise<AIDocument> => {
      const updated = await docmgrApi.update(id, data);
      setDocs((prev) => prev.map((d) => (d.id === id ? updated : d)));
      return updated;
    },
    []
  );

  const deleteDoc = useCallback(async (id: string) => {
    await docmgrApi.delete(id);
    setDocs((prev) => prev.filter((d) => d.id !== id));
    setTotal((prev) => prev - 1);
  }, []);

  const toggleStar = useCallback(
    async (id: string, current: boolean) => {
      return updateDoc(id, { is_starred: !current });
    },
    [updateDoc]
  );

  return {
    docs,
    total,
    loading,
    page,
    pageSize,
    setPage: (p: number) => {
      setPage(p);
      load(p, filterRef.current);
    },
    setFilter,
    folders,
    createDoc,
    deleteDoc,
    toggleStar,
  };
}
