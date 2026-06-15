"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "app-center-favorites";

/**
 * 应用收藏状态管理。
 *
 * 持久化到 localStorage（key: app-center-favorites），跨会话保持。
 * 使用 'use client' + useEffect 守卫处理 Next.js SSR（localStorage 在服务端不存在）。
 * 水合前返回空集合，避免服务端/客户端渲染不一致。
 */
export function useFavorites() {
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [hydrated, setHydrated] = useState(false);

  // 水合：从 localStorage 读取
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setFavorites(new Set(parsed.filter((x) => typeof x === "string")));
        }
      }
    } catch {
      // 解析失败或 localStorage 不可用 —— 静默回退到空集合
    }
    setHydrated(true);
  }, []);

  // 持久化
  const persist = useCallback((next: Set<string>) => {
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(Array.from(next)),
      );
    } catch {
      // 写入失败（隐私模式 / 配额）—— 静默忽略
    }
  }, []);

  const toggleFavorite = useCallback(
    (appId: string) => {
      setFavorites((prev) => {
        const next = new Set(prev);
        if (next.has(appId)) {
          next.delete(appId);
        } else {
          next.add(appId);
        }
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const isFavorite = useCallback(
    (appId: string) => favorites.has(appId),
    [favorites],
  );

  return {
    favorites,
    favoriteIds: Array.from(favorites),
    isFavorite,
    toggleFavorite,
    /** localStorage 是否已完成水合（水合前为 false，避免闪烁误判） */
    hydrated,
  };
}
