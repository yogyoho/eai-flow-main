"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, use, type ReactNode } from "react";

import SimpleShellLayout from "@/app/extensions/shell-old/SimpleShellLayout";
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

  // EAI-CUSTOM: 必须包在 SimpleShellLayout(内含 PermissionProvider+AuthProvider)内，
  // 否则 KnowledgeBaseDetail 调用 usePermission 会抛 "must be used within a PermissionProvider"
  let content: ReactNode;
  if (isLoading) {
    content = <div className="p-8 text-sm text-muted-foreground">加载中…</div>;
  } else if (error || !kb) {
    content = (
      <div className="p-8 text-sm text-muted-foreground">
        知识库不存在或无权访问。
        <button className="ml-2 underline" onClick={() => router.push("/knowledge")}>
          返回列表
        </button>
      </div>
    );
  } else {
    content = (
      <KnowledgeBaseDetail kb={kb} onBack={() => router.push("/knowledge")} onKbUpdated={setKb} />
    );
  }

  return <SimpleShellLayout>{content}</SimpleShellLayout>;
}
