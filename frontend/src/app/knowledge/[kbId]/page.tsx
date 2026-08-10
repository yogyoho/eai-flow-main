"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, use } from "react";

import { kbApi } from "@/extensions/api";
import type { KnowledgeBase } from "@/extensions/types";

import { KnowledgeBaseDetail } from "../_components/KnowledgeBaseDetail";

export default function KnowledgeBaseDetailPage({
  params,
}: {
  params: Promise<{ kbId: string }>;
}) {
  const { kbId } = use(params);
  const router = useRouter();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    kbApi
      .get(kbId)
      .then((res) => {
        if (cancelled) return;
        setKb(res);
        setError(false);
      })
      .catch(() => {
        if (cancelled) return;
        setError(true);
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [kbId]);

  if (isLoading) {
    return <div className="p-8 text-sm text-muted-foreground">加载中…</div>;
  }
  if (error || !kb) {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        知识库不存在或无权访问。
        <button className="ml-2 underline" onClick={() => router.push("/knowledge")}>
          返回列表
        </button>
      </div>
    );
  }

  return (
    <KnowledgeBaseDetail
      kb={kb}
      onBack={() => router.push("/knowledge")}
      onKbUpdated={setKb}
    />
  );
}
