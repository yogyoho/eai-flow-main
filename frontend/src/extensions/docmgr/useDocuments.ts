"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SetStateAction } from "react";

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
  const [filter, setFilter] = useState<DocumentFilter>(initialFilter ?? { folder: "默认文件夹" });

  const filterRef = useRef<DocumentFilter>(filter);
  const pageRef = useRef<number>(page);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await docmgrApi.list({
        folder: filterRef.current.folder,
        starred: filterRef.current.starred,
        shared: filterRef.current.shared,
        q: filterRef.current.q,
        skip: (pageRef.current - 1) * PAGE_SIZE,
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

  useEffect(() => {
    filterRef.current = filter;
  }, [filter]);

  useEffect(() => {
    pageRef.current = page;
  }, [page]);

  useEffect(() => {
    load();
  }, [filter, page, load]);

  const handleSetFilter = useCallback((nextFilter: SetStateAction<DocumentFilter>) => {
    setFilter((prev) => (typeof nextFilter === "function" ? nextFilter(prev) : nextFilter));
    setPage(1);
  }, []);

  const createDoc = useCallback(
    async (data: CreateAIDocumentRequest) => {
      const doc = await docmgrApi.create(data);
      await load();
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
    setPage,
    setFilter: handleSetFilter,
    folders,
    createDoc,
    deleteDoc,
    toggleStar,
  };
}
