"use client"

import { useState, useCallback, useEffect } from "react";
import { docmgrApi } from "../api";

// EAI-CUSTOM: 项目区 outputs（跨用户共享文件系统视图）
// 与个人区不同——项目文件是扁平 list（每个文件带 thread_id + member），
// 无需按线程分组分页；单次拉全量（项目 outputs 数量有限）。
export interface ProjectDocFile {
  name: string;
  rel_path: string;
  size: number;
  mime: string;
  modified_at: string;
  member: string;
  thread_id: string;
}

export function useProjectOutputs(projectId: string | null | undefined) {
  const [files, setFiles] = useState<ProjectDocFile[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!projectId) {
      setFiles([]);
      setTotal(0);
      return;
    }
    setLoading(true);
    try {
      const data = await docmgrApi.listProjectOutputs(projectId);
      setFiles(data.files);
      setTotal(data.total);
    } catch (err) {
      console.error("Failed to fetch project outputs:", err);
      setFiles([]);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { files, total, loading, refresh };
}
